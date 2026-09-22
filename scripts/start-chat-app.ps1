<#
.SYNOPSIS
Starts the local Private Chat backend and frontend together.

.DESCRIPTION
Starts only loopback processes: FastAPI for encrypted local storage and the
React/Vite frontend. It never starts AWS infrastructure or opens a public port.
Use -Restart to stop this project's existing services before starting them.
#>
[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$BackendPort = 8000,
    [ValidateRange(1024, 65535)]
    [int]$FrontendPort = 5173,
    [switch]$Restart,
    [switch]$KeepOpenOnError,
    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

trap {
    Write-Host "Private Chat could not start: $($_.Exception.Message)" -ForegroundColor Red
    if ($KeepOpenOnError) { Read-Host 'Press Enter to close' | Out-Null }
    exit 1
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendDirectory = Join-Path $repositoryRoot 'backend'
$frontendDirectory = Join-Path $repositoryRoot 'frontend'
$backendEnvironment = Join-Path $backendDirectory '.env'
$logDirectory = Join-Path $repositoryRoot '.local\runtime-logs'
$frontendUrl = "http://127.0.0.1:$FrontendPort"

# Serialize repeated double-clicks, including readiness checks and browser launch.
$launchMutex = New-Object System.Threading.Mutex($false, 'Local\PrivateLLMChatLauncher')
try { $lockAcquired = $launchMutex.WaitOne(0) }
catch [System.Threading.AbandonedMutexException] { $lockAcquired = $true }
if (-not $lockAcquired) {
    Write-Host 'Private Chat is already starting. Please wait for the browser.'
    $launchMutex.Dispose()
    exit 0
}

try {

function Stop-ProjectListener {
    param([int]$Port)
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
        $candidate = $owner
        $belongsToProject = $false
        # Python's venv launcher can be the listener's parent on Windows.
        for ($depth = 0; $depth -lt 3 -and $null -ne $candidate; $depth++) {
            if (($candidate.ExecutablePath -and $candidate.ExecutablePath.StartsWith($repositoryRoot + '\', [StringComparison]::OrdinalIgnoreCase)) -or
                ($candidate.CommandLine -and $candidate.CommandLine.IndexOf($repositoryRoot + '\', [StringComparison]::OrdinalIgnoreCase) -ge 0)) {
                $belongsToProject = $true
                break
            }
            $candidate = Get-CimInstance Win32_Process -Filter "ProcessId = $($candidate.ParentProcessId)"
        }
        if (-not $belongsToProject -or $owner.Name -notin @('python.exe', 'pythonw.exe', 'node.exe', 'bun.exe')) {
            throw "Port $Port is used by another program (PID $($listener.OwningProcess)); it was not stopped."
        }
        Write-Host "Stopping Private Chat on port $Port..."
        Stop-Process -Id $listener.OwningProcess -Force
    }
    $deadline = (Get-Date).AddSeconds(10)
    while (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
        if ((Get-Date) -ge $deadline) { throw "Port $Port did not close after stopping Private Chat." }
        Start-Sleep -Milliseconds 200
    }
}

function Test-ListeningPort {
    param(
        [int]$Port,
        [string]$Address = '127.0.0.1'
    )
    return $null -ne (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object LocalAddress -EQ $Address |
        Select-Object -First 1)
}

function Wait-ForLocalUrl {
    param(
        [string]$Url,
        [string]$Name,
        [string]$DiagnosticsLog,
        [System.Diagnostics.Process]$ServiceProcess
    )
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        if ($ServiceProcess -and $ServiceProcess.HasExited) { break }
        try {
            Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing | Out-Null
            return
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }

    $message = "$Name did not become ready."
    if ($DiagnosticsLog -and (Test-Path -LiteralPath $DiagnosticsLog)) {
        $details = (Get-Content -LiteralPath $DiagnosticsLog -Tail 20) -join [Environment]::NewLine
        if (-not [string]::IsNullOrWhiteSpace($details)) {
            $message += " Latest startup error from ${DiagnosticsLog}:$([Environment]::NewLine)$details"
        } else {
            $message += " See $DiagnosticsLog."
        }
    } else {
        $message += " See $logDirectory for its local startup log."
    }
    throw $message
}

function Resolve-LocalCommand {
    param(
        [string]$Name,
        [string[]]$FallbackPaths,
        [string]$InstallHint
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }
    foreach ($candidate in $FallbackPaths) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "$Name is required but was not found. $InstallHint"
}

if (-not (Test-Path -LiteralPath $backendEnvironment)) {
    throw "Create $backendEnvironment from backend\.env.example and set CHAT_OPENROUTER_API_KEY first."
}

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$runStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$pythonPath = Join-Path $backendDirectory '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'The backend virtual environment is missing.' }
$codexRuntimeRoot = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
$nodePath = Resolve-LocalCommand 'node' @(
    (Join-Path $env:ProgramFiles 'nodejs\node.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\nodejs\node.exe'),
    (Join-Path $codexRuntimeRoot 'node\bin\node.exe')
) 'Install Node.js and open a new PowerShell window.'
$vitePath = Join-Path $frontendDirectory 'node_modules\vite\bin\vite.js'
if (-not (Test-Path -LiteralPath $vitePath)) { throw 'Frontend dependencies are missing. Run pnpm install in frontend.' }
if ($Restart) {
    Stop-ProjectListener $FrontendPort
    Stop-ProjectListener $BackendPort
}
$backendProcess = $null
$frontendProcess = $null

if (-not (Test-ListeningPort $BackendPort)) {
    $pythonPath = Join-Path $backendDirectory '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        $pythonPath = (Get-Command python -ErrorAction Stop).Source
    }
    $backendErrorLog = Join-Path $logDirectory "backend-$runStamp.err.log"
    $backendProcess = Start-Process -FilePath $pythonPath `
        -ArgumentList @('-m', 'uvicorn', 'private_chat.main:app', '--host', '127.0.0.1', '--port', $BackendPort) `
        -WorkingDirectory $backendDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDirectory "backend-$runStamp.out.log") `
        -RedirectStandardError $backendErrorLog -PassThru
} else {
    $backendErrorLog = ''
}
Wait-ForLocalUrl "http://127.0.0.1:$BackendPort/v1/health" 'Backend' $backendErrorLog $backendProcess

if (-not (Test-ListeningPort $FrontendPort)) {
    $codexRuntimeRoot = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
    $nodePath = Resolve-LocalCommand 'node' @(
        (Join-Path $env:ProgramFiles 'nodejs\node.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\nodejs\node.exe'),
        (Join-Path $codexRuntimeRoot 'node\bin\node.exe')
    ) 'Install Node.js 20.19 or later, then open a new PowerShell window.'
    $nodeDirectory = Split-Path -Parent $nodePath
    $env:Path = "$nodeDirectory;$env:Path"

    $frontendErrorLog = Join-Path $logDirectory "frontend-$runStamp.err.log"
    $frontendProcess = Start-Process -FilePath $nodePath `
        -ArgumentList @(('"' + $vitePath + '"'), '--host', '127.0.0.1', '--port', $FrontendPort, '--strictPort') `
        -WorkingDirectory $frontendDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDirectory "frontend-$runStamp.out.log") `
        -RedirectStandardError $frontendErrorLog -PassThru
} else {
    $frontendErrorLog = ''
}
Wait-ForLocalUrl $frontendUrl 'Frontend' $frontendErrorLog $frontendProcess

Write-Host "Private Chat is running at $frontendUrl"
if (-not $NoBrowser) { Start-Process $frontendUrl }
} finally {
    $launchMutex.ReleaseMutex()
    $launchMutex.Dispose()
}

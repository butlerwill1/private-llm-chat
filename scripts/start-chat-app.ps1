<#
.SYNOPSIS
Starts the local Private Chat backend and frontend together.

.DESCRIPTION
Starts only loopback processes: FastAPI for encrypted local storage and the
React/Vite frontend. It never starts AWS infrastructure or opens a public port.
If either configured port is already listening, that existing process is reused.
#>
[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$BackendPort = 8000,
    [ValidateRange(1024, 65535)]
    [int]$FrontendPort = 5173
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendDirectory = Join-Path $repositoryRoot 'backend'
$frontendDirectory = Join-Path $repositoryRoot 'frontend'
$backendEnvironment = Join-Path $backendDirectory '.env'
$logDirectory = Join-Path $repositoryRoot '.local\runtime-logs'
$frontendUrl = "http://127.0.0.1:$FrontendPort"

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
        [string]$DiagnosticsLog
    )
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
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
$runStamp = Get-Date -Format 'yyyyMMdd-HHmmss'

if (-not (Test-ListeningPort $BackendPort)) {
    $pythonPath = Join-Path $backendDirectory '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        $pythonPath = (Get-Command python -ErrorAction Stop).Source
    }
    $backendErrorLog = Join-Path $logDirectory "backend-$runStamp.err.log"
    Start-Process -FilePath $pythonPath `
        -ArgumentList @('-m', 'uvicorn', 'private_chat.main:app', '--host', '127.0.0.1', '--port', $BackendPort) `
        -WorkingDirectory $backendDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDirectory "backend-$runStamp.out.log") `
        -RedirectStandardError $backendErrorLog | Out-Null
} else {
    $backendErrorLog = ''
}
Wait-ForLocalUrl "http://127.0.0.1:$BackendPort/v1/health" 'Backend' $backendErrorLog

if (-not (Test-ListeningPort $FrontendPort)) {
    $codexRuntimeRoot = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
    $nodePath = Resolve-LocalCommand 'node' @(
        (Join-Path $env:ProgramFiles 'nodejs\node.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\nodejs\node.exe'),
        (Join-Path $codexRuntimeRoot 'node\bin\node.exe')
    ) 'Install Node.js 20.19 or later, then open a new PowerShell window.'
    $nodeDirectory = Split-Path -Parent $nodePath
    $env:Path = "$nodeDirectory;$env:Path"

    $pnpmPath = Resolve-LocalCommand 'pnpm' @(
        (Join-Path $codexRuntimeRoot 'bin\fallback\pnpm.cmd')
    ) 'Install pnpm 11, then open a new PowerShell window.'
    $frontendErrorLog = Join-Path $logDirectory "frontend-$runStamp.err.log"
    Start-Process -FilePath $pnpmPath `
        -ArgumentList @('run', 'dev', '--host', '127.0.0.1', '--port', $FrontendPort) `
        -WorkingDirectory $frontendDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDirectory "frontend-$runStamp.out.log") `
        -RedirectStandardError $frontendErrorLog | Out-Null
} else {
    $frontendErrorLog = ''
}
Wait-ForLocalUrl $frontendUrl 'Frontend' $frontendErrorLog

Write-Host "Private Chat is running at $frontendUrl"
Start-Process $frontendUrl

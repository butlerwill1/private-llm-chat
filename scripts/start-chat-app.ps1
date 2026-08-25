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
    param([int]$Port)
    return $null -ne (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1)
}

function Wait-ForLocalUrl {
    param([string]$Url, [string]$Name)
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing | Out-Null
            return
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "$Name did not become ready. See $logDirectory for its local startup log."
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
    Start-Process -FilePath $pythonPath `
        -ArgumentList @('-m', 'uvicorn', 'private_chat.main:app', '--host', '127.0.0.1', '--port', $BackendPort) `
        -WorkingDirectory $backendDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDirectory "backend-$runStamp.out.log") `
        -RedirectStandardError (Join-Path $logDirectory "backend-$runStamp.err.log") | Out-Null
}
Wait-ForLocalUrl "http://127.0.0.1:$BackendPort/v1/health" 'Backend'

if (-not (Test-ListeningPort $FrontendPort)) {
    $pnpmPath = (Get-Command pnpm -ErrorAction Stop).Source
    Start-Process -FilePath $pnpmPath `
        -ArgumentList @('run', 'dev', '--', '--host', '127.0.0.1', '--port', $FrontendPort) `
        -WorkingDirectory $frontendDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDirectory "frontend-$runStamp.out.log") `
        -RedirectStandardError (Join-Path $logDirectory "frontend-$runStamp.err.log") | Out-Null
}
Wait-ForLocalUrl $frontendUrl 'Frontend'

Write-Host "Private Chat is running at $frontendUrl"
Start-Process $frontendUrl

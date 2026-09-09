<#
.SYNOPSIS
Prepares the supported laptop-local Ollama model without contacting AWS.
#>
[CmdletBinding()]
param(
    [string]$Model = 'gemma3:4b'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    throw 'NVIDIA drivers and nvidia-smi are required before configuring local GPU inference.'
}
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

$ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollamaCommand) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'Install Ollama for Windows, then run this script again. winget was not found.'
    }
    Write-Host 'Installing Ollama for the current laptop…'
    winget install --id Ollama.Ollama --exact --accept-package-agreements --accept-source-agreements
    # winget updates PATH for new processes only. Resolve the standard per-user
    # install path so first-time setup can continue in this same terminal.
    $installedOllama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (-not (Test-Path -LiteralPath $installedOllama)) {
        throw 'Ollama installed but its executable was not found. Open a new PowerShell window and run this script again.'
    }
    $ollamaPath = $installedOllama
} else {
    $ollamaPath = $ollamaCommand.Source
}

& $ollamaPath pull $Model

# Use Ollama's local HTTP API for readiness instead of its terminal UI. The CLI
# writes animated Unicode progress glyphs to stderr while loading, which PowerShell
# can otherwise promote into a misleading NativeCommandError.
$body = @{
    model = $Model
    prompt = 'Reply with exactly: local model ready'
    stream = $false
    options = @{ temperature = 0; num_predict = 12 }
} | ConvertTo-Json -Depth 3
$reply = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/generate' `
    -ContentType 'application/json' -Body $body
if ($reply.response -notmatch 'local model ready') {
    throw 'Ollama installed the model but the local readiness completion did not pass.'
}

$running = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/ps'
$loaded = @($running.models | Where-Object { $_.name -eq $Model }) | Select-Object -First 1
if ($null -eq $loaded -or [int64]$loaded.size_vram -le 0) {
    throw @"
Ollama completed a CPU inference, but did not load $Model into GPU VRAM.
Run 'ollama ps' and inspect %LOCALAPPDATA%\Ollama\server.log for GPU discovery errors.
Do not treat this setup as GPU-ready until 'ollama ps' reports a non-zero VRAM allocation.
"@
}

$envFile = Join-Path $PSScriptRoot '..\backend\.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Create $envFile from backend\.env.example before enabling the local model."
}
Write-Host "Local Ollama model $Model is ready. Add CHAT_ENABLE_LOCAL_OLLAMA=true to backend\.env, then start Private Chat."

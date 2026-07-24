<#
.SYNOPSIS
Starts the local FastAPI backend in OpenRouter-only mode.

.DESCRIPTION
This helper deliberately performs no AWS, EC2, SSM or GPU action. It reads an
OpenRouter API key and the privacy-approved provider allowlist from the current
process environment, then runs the same local API used by the React frontend.
#>
[CmdletBinding()]
param(
    [string[]]$Models = @(
        'meta-llama/llama-3.3-70b-instruct',
        'qwen/qwen3-32b',
        'deepseek/deepseek-r1',
        'mistralai/mistral-small-3.1-24b-instruct',
        'google/gemma-3-27b-it'
    ),

    [switch]$AllowCustomModel,

    [ValidateRange(1024, 65535)]
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($env:CHAT_OPENROUTER_API_KEY)) {
    throw 'Set CHAT_OPENROUTER_API_KEY in this PowerShell session before starting OpenRouter mode.'
}
if ([string]::IsNullOrWhiteSpace($env:CHAT_OPENROUTER_ALLOWED_PROVIDERS)) {
    throw 'Set CHAT_OPENROUTER_ALLOWED_PROVIDERS to your reviewed privacy-approved provider slugs first.'
}
if ($Models.Count -eq 0) {
    throw 'At least one OpenRouter model must be configured.'
}

# These variables affect only this local backend process and are intentionally
# explicit: OpenRouter mode must not accidentally require or start the GPU.
$env:CHAT_MODEL_BACKEND = 'openrouter'
$env:CHAT_ENABLE_OPENROUTER = 'true'
$env:CHAT_OPENROUTER_MODELS = ($Models -join ',')
$env:CHAT_ALLOW_CUSTOM_OPENROUTER_MODEL = if ($AllowCustomModel) { 'true' } else { 'false' }

$backendDirectory = Join-Path $PSScriptRoot '..\backend'
Push-Location $backendDirectory
try {
    Write-Host 'Starting OpenRouter-only backend. No GPU instance will be started.'
    python -m uvicorn private_chat.main:app --host 127.0.0.1 --port $Port
} finally {
    Pop-Location
}

<#
.SYNOPSIS
Starts the normal local encrypted OpenRouter chat backend.

.DESCRIPTION
This launcher reads only local backend configuration, validates OpenRouter's
ZDR catalogue during FastAPI startup, and binds to loopback. It never invokes
Terraform, AWS CLI, EC2, SSM, S3, or KMS.
#>
[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$backendDirectory = Join-Path $PSScriptRoot '..\backend'
$envFile = Join-Path $backendDirectory '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Create $envFile from .env.example and set CHAT_OPENROUTER_API_KEY first."
}

Push-Location $backendDirectory
try {
    Write-Host 'Starting loopback-only local encrypted chat. No AWS resources will be used.'
    python -m uvicorn private_chat.main:app --host 127.0.0.1 --port $Port
} finally {
    Pop-Location
}

<#
.SYNOPSIS
Compatibility launcher for the OpenRouter backend.

.DESCRIPTION
Use start-local-chat.ps1 for new sessions. This wrapper remains so existing
documentation or shortcuts keep working; it uses the same encrypted local
storage and reviewed provider routes and never starts AWS resources.
#>
[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Warning 'start-openrouter-backend.ps1 is retained for compatibility. Use start-local-chat.ps1 for new sessions.'
& (Join-Path $PSScriptRoot 'start-local-chat.ps1') -Port $Port

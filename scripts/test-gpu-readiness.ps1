<#
.SYNOPSIS
Runs the full Ollama text, vision, scheduler, and GPU readiness test over SSM.

.DESCRIPTION
Uploads the repository's versioned Bash probe to one explicitly selected EC2
instance through an SSM Run Command. The probe calls Ollama only on the
instance's loopback interface, so it does not expose port 11434 or alter the
existing local SSM tunnel.

On failure, the remote probe captures systemd status, the recent Ollama
journal, nvidia-smi, /api/ps, process state, memory, storage, and kernel OOM
events in /var/log/private-llm-chat.

.PARAMETER InstanceId
The existing private GPU EC2 instance to test.

.PARAMETER Model
The one installed Ollama model that must be tested. No model is pulled or
substituted.

.PARAMETER WarmRuns
Number of consecutive warm vision requests after the first vision request.

.PARAMETER Region
AWS region containing the instance.

.EXAMPLE
.\scripts\test-gpu-readiness.ps1 -InstanceId i-0123456789abcdef0
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^i-[0-9a-f]{8,17}$')]
    [string]$InstanceId,

    [ValidateNotNullOrEmpty()]
    [string]$Model = 'private-vision',

    [ValidateRange(1, 20)]
    [int]$WarmRuns = 5,

    [ValidateNotNullOrEmpty()]
    [string]$Region = 'eu-west-2'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$probePath = Join-Path $repoRoot 'terraform\modules\image_builder\scripts\verify-ollama-readiness.sh'

if (-not (Test-Path -LiteralPath $probePath -PathType Leaf)) {
    throw "Readiness probe not found: $probePath"
}

# Base64 keeps the multi-line Bash source intact while it passes through the
# Windows AWS CLI, JSON, SSM, and the remote shell.
$probeBytes = [System.IO.File]::ReadAllBytes($probePath)
$encodedProbe = [Convert]::ToBase64String($probeBytes)
$remoteProbe = '/tmp/private-llm-chat-verify-ollama-readiness'
$remoteCommand = @(
    "printf '%s' '$encodedProbe' | base64 --decode >$remoteProbe"
    "chmod 0700 $remoteProbe"
    "$remoteProbe '$Model' $WarmRuns"
    'exit_code=$?'
    "rm --force $remoteProbe"
    'exit $exit_code'
) -join '; '

Write-Host "Starting readiness test on $InstanceId for model '$Model'..."
$requestPath = Join-Path ([IO.Path]::GetTempPath()) "private-llm-chat-readiness-$([guid]::NewGuid()).json"
$request = @{
    InstanceIds  = @($InstanceId)
    DocumentName = 'AWS-RunShellScript'
    Comment      = 'Private Ollama GPU readiness test'
    Parameters   = @{
        commands = @($remoteCommand)
    }
} | ConvertTo-Json -Depth 5

try {
    # Supplying a JSON file avoids Windows AWS CLI shorthand parsing, which
    # treats quotes and semicolons inside the encoded remote command as syntax.
    [IO.File]::WriteAllText(
        $requestPath,
        $request,
        [Text.UTF8Encoding]::new($false)
    )
    $commandId = aws ssm send-command `
        --region $Region `
        --cli-input-json "file://$requestPath" `
        --query 'Command.CommandId' `
        --output text `
        --no-cli-pager
}
finally {
    Remove-Item -LiteralPath $requestPath -Force -ErrorAction SilentlyContinue
}

if (-not $commandId -or $LASTEXITCODE -ne 0) {
    throw 'AWS did not accept the SSM readiness command.'
}

Write-Host "SSM command: $commandId"
# The built-in AWS waiter gives up after roughly 100 seconds, which is shorter
# than the deliberately generous cold-load timeout. Poll terminal SSM states
# ourselves for up to 20 minutes.
$terminalStatuses = @('Success', 'Cancelled', 'TimedOut', 'Failed', 'Cancelling')
$commandStatus = $null
for ($attempt = 1; $attempt -le 240; $attempt++) {
    $commandStatus = aws ssm get-command-invocation `
        --region $Region `
        --command-id $commandId `
        --instance-id $InstanceId `
        --query 'Status' `
        --output text `
        --no-cli-pager 2>$null

    if ($LASTEXITCODE -eq 0 -and $terminalStatuses -contains $commandStatus) {
        break
    }
    Start-Sleep -Seconds 5
}

if ($terminalStatuses -notcontains $commandStatus) {
    throw "SSM readiness command $commandId did not reach a terminal state within 20 minutes."
}

$invocationJson = aws ssm get-command-invocation `
    --region $Region `
    --command-id $commandId `
    --instance-id $InstanceId `
    --output json `
    --no-cli-pager

if ($LASTEXITCODE -ne 0) {
    throw "Could not retrieve SSM command result $commandId."
}

$invocation = $invocationJson | ConvertFrom-Json
if ($invocation.StandardOutputContent) {
    Write-Host $invocation.StandardOutputContent
}
if ($invocation.StandardErrorContent) {
    [Console]::Error.WriteLine($invocation.StandardErrorContent)
}

if ($invocation.Status -ne 'Success' -or $invocation.ResponseCode -ne 0) {
    throw "Ollama readiness failed with SSM status '$($invocation.Status)' and exit code $($invocation.ResponseCode)."
}

Write-Host 'Ollama text, vision, scheduler, and GPU readiness passed.'

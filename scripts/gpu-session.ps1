<#
.SYNOPSIS
Starts the private GPU and opens either an Ollama tunnel or command-line shell.

.DESCRIPTION
The EC2 instance has no public IP and no inbound management port. This script
waits for its outbound SSM Agent connection, then asks Session Manager for an
authenticated encrypted session. By default it stops the GPU when the session
ends so an abandoned terminal does not leave chargeable compute running.
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^i-[0-9a-f]+$')]
    [string]$InstanceId,

    [ValidateSet('Tunnel', 'Shell')]
    [string]$Mode = 'Tunnel',

    [ValidateRange(1024, 65535)]
    [int]$LocalPort = 11434,

    [ValidateRange(1024, 65535)]
    [int]$RemotePort = 11434,

    [ValidatePattern('^[a-z]{2}-[a-z]+-[0-9]+$')]
    [string]$Region = 'eu-west-2',

    [ValidatePattern('^[A-Za-z0-9_+=,.@-]+$')]
    [string]$Profile,

    [ValidateRange(60, 900)]
    [int]$ReadyTimeoutSeconds = 420,

    [switch]$LeaveRunning
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-AwsArguments {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $common = @('--region', $Region, '--no-cli-pager')
    if ($Profile) {
        $common += @('--profile', $Profile)
    }
    return @($Arguments + $common)
}

function Invoke-AwsJson {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = & aws @(Get-AwsArguments -Arguments $Arguments)
    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI failed with exit code $LASTEXITCODE."
    }
    return ($output | ConvertFrom-Json)
}

function Initialize-SessionManagerPlugin {
    <#
    Makes the AWS Session Manager plugin visible to this process.

    The official Windows installer normally updates PATH only for new shells.
    Resolving its standard installation location keeps a just-installed plugin
    usable immediately, while still producing a clear error if it is absent.
    #>
    $pluginCommand = Get-Command -Name 'session-manager-plugin' -ErrorAction SilentlyContinue
    if ($pluginCommand) {
        return
    }

    $pluginDirectory = Join-Path $env:ProgramFiles 'Amazon\SessionManagerPlugin\bin'
    $pluginPath = Join-Path $pluginDirectory 'session-manager-plugin.exe'
    if (-not (Test-Path -LiteralPath $pluginPath -PathType Leaf)) {
        throw @"
The AWS Session Manager plugin is required for private shells and port forwarding.
Install it from the official AWS documentation, then run this script again.
"@
    }

    # AWS CLI discovers the plugin by executable name, so prepend the verified
    # official installation directory only for this script's child processes.
    $env:Path = "$pluginDirectory;$env:Path"
    $null = Get-Command -Name 'session-manager-plugin' -ErrorAction Stop
}

$null = Get-Command -Name 'aws' -ErrorAction Stop
Initialize-SessionManagerPlugin
$instance = Invoke-AwsJson -Arguments @(
    'ec2', 'describe-instances', '--instance-ids', $InstanceId, '--output', 'json'
)
$state = [string]$instance.Reservations[0].Instances[0].State.Name
if ($state -notin @('pending', 'running', 'stopped')) {
    throw "Instance '$InstanceId' is in state '$state' and cannot start a personal session."
}

$sessionAction = if ($Mode -eq 'Shell') { 'Open private command-line session' } else { 'Open private Ollama tunnel' }
if (-not $PSCmdlet.ShouldProcess($InstanceId, $sessionAction)) {
    return
}

try {
    if ($state -eq 'stopped') {
        if (-not $PSCmdlet.ShouldProcess($InstanceId, 'Start chargeable GPU instance')) {
            return
        }
        $null = Invoke-AwsJson -Arguments @(
            'ec2', 'start-instances', '--instance-ids', $InstanceId, '--output', 'json'
        )
    }

    Write-Host 'Waiting for the EC2 instance to enter the running state...'
    & aws @(Get-AwsArguments -Arguments @('ec2', 'wait', 'instance-running', '--instance-ids', $InstanceId))
    if ($LASTEXITCODE -ne 0) {
        throw 'The GPU instance did not reach the running state.'
    }

    Write-Host 'Waiting for the private SSM Agent connection...'
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($ReadyTimeoutSeconds)
    $online = $false
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        $information = Invoke-AwsJson -Arguments @(
            'ssm', 'describe-instance-information',
            '--filters', "Key=InstanceIds,Values=$InstanceId", '--output', 'json'
        )
        $online = @($information.InstanceInformationList).Count -eq 1 -and
            $information.InstanceInformationList[0].PingStatus -eq 'Online'
        if ($online) {
            break
        }
        Start-Sleep -Seconds 5
    }
    if (-not $online) {
        throw @"
The SSM Agent did not become online. Confirm enable_ssm_endpoints=true has been
applied, the endpoint security group allows HTTPS, and the GPU role includes
AmazonSSMManagedInstanceCore.
"@
    }

    if ($Mode -eq 'Shell') {
        Write-Host 'Opening a command-line shell. Type exit to close it.'
        & aws @(Get-AwsArguments -Arguments @('ssm', 'start-session', '--target', $InstanceId))
    } else {
        Write-Host "Forwarding http://127.0.0.1:$LocalPort to Ollama on the private GPU."
        Write-Host 'Keep this window open while using the chat. Press Ctrl+C to finish.'
        $parameters = ConvertTo-Json -Compress -InputObject @{
            portNumber      = @([string]$RemotePort)
            localPortNumber = @([string]$LocalPort)
        }
        # Windows PowerShell removes JSON quotation marks when a raw JSON string
        # is forwarded to a native executable. Escape them once so AWS CLI receives
        # a valid map of string lists rather than an invalid shorthand value.
        $escapedParameters = $parameters.Replace('"', '\"')
        & aws @(Get-AwsArguments -Arguments @(
            'ssm', 'start-session', '--target', $InstanceId,
            '--document-name', 'AWS-StartPortForwardingSession',
            '--parameters', $escapedParameters
        ))
    }
    if ($LASTEXITCODE -ne 0) {
        throw 'The Systems Manager session ended with an error.'
    }
} finally {
    # Cost safety wins even if readiness or session establishment fails: unless
    # explicitly overridden, this helper never intentionally leaves a GPU running.
    if (-not $LeaveRunning) {
        if ($PSCmdlet.ShouldProcess($InstanceId, 'Stop chargeable GPU instance')) {
            Write-Host 'Stopping the GPU instance...'
            $null = Invoke-AwsJson -Arguments @(
                'ec2', 'stop-instances', '--instance-ids', $InstanceId, '--output', 'json'
            )
            Write-Host 'Stop requested. Disable the SSM endpoints with Terraform after EC2 reports stopped.'
        }
    } elseif ($LeaveRunning) {
        Write-Warning "GPU instance '$InstanceId' is still running and accruing charges."
    }
}

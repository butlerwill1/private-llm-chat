<# Emergency cost-control helper for stopping the private GPU after a lost session. #>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^i-[0-9a-f]+$')]
    [string]$InstanceId,

    [ValidatePattern('^[a-z]{2}-[a-z]+-[0-9]+$')]
    [string]$Region = 'eu-west-2',

    [ValidatePattern('^[A-Za-z0-9_+=,.@-]+$')]
    [string]$Profile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$null = Get-Command -Name 'aws' -ErrorAction Stop

$arguments = @('ec2', 'stop-instances', '--instance-ids', $InstanceId, '--region', $Region, '--no-cli-pager')
if ($Profile) {
    $arguments += @('--profile', $Profile)
}

if ($PSCmdlet.ShouldProcess($InstanceId, 'Stop chargeable GPU instance')) {
    & aws @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI failed with exit code $LASTEXITCODE."
    }
}

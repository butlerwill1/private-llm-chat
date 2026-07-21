[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')]
    [string]$Repository,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$Revision,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._/-]*\.gguf$')]
    [string]$Filename,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$')]
    [string]$BucketName,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^arn:aws[^:]*:kms:[a-z0-9-]+:[0-9]{12}:key/[0-9a-fA-F-]+$')]
    [string]$KmsKeyArn,

    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$')]
    [string]$ModelName = 'private',

    [ValidatePattern('^[0-9a-fA-F]{64}$')]
    [string]$ExpectedSha256,

    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._/-]*$')]
    [string]$DestinationKey,

    [switch]$KeepDownload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command '$Command' failed with exit code $LASTEXITCODE."
    }
}

function Get-HuggingFaceFileDigest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ModelRepository,

        [Parameter(Mandatory = $true)]
        [string]$Commit,

        [Parameter(Mandatory = $true)]
        [string]$ModelFilename
    )

    $encodedRepository = [Uri]::EscapeDataString($ModelRepository).Replace('%2F', '/')
    $metadataUrl = "https://huggingface.co/api/models/$encodedRepository/revision/$Commit`?blobs=true"
    $metadata = Invoke-RestMethod -Uri $metadataUrl -Method Get
    $file = @($metadata.siblings) | Where-Object { $_.rfilename -eq $ModelFilename } | Select-Object -First 1

    if ($null -eq $file) {
        throw "'$ModelFilename' was not found in $ModelRepository at revision $Commit."
    }
    if ($null -eq $file.lfs -or [string]::IsNullOrWhiteSpace([string]$file.lfs.sha256)) {
        throw 'Hugging Face did not publish an LFS SHA-256 for this file; supply -ExpectedSha256 explicitly.'
    }

    return ([string]$file.lfs.sha256).ToLowerInvariant()
}

function Assert-ModelBucketControls {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedKmsKeyArn
    )

    $publicAccess = Invoke-NativeCommand -Command 'aws' -Arguments @(
        's3api', 'get-public-access-block', '--bucket', $Name, '--output', 'json'
    ) | ConvertFrom-Json
    $block = $publicAccess.PublicAccessBlockConfiguration
    if (-not ($block.BlockPublicAcls -and $block.IgnorePublicAcls -and $block.BlockPublicPolicy -and $block.RestrictPublicBuckets)) {
        throw "Bucket '$Name' does not have every S3 Block Public Access control enabled."
    }

    $versioning = Invoke-NativeCommand -Command 'aws' -Arguments @(
        's3api', 'get-bucket-versioning', '--bucket', $Name, '--output', 'json'
    ) | ConvertFrom-Json
    if ($versioning.Status -ne 'Enabled') {
        throw "Bucket '$Name' does not have versioning enabled."
    }

    $encryption = Invoke-NativeCommand -Command 'aws' -Arguments @(
        's3api', 'get-bucket-encryption', '--bucket', $Name, '--output', 'json'
    ) | ConvertFrom-Json
    $defaultEncryption = @($encryption.ServerSideEncryptionConfiguration.Rules)[0].ApplyServerSideEncryptionByDefault
    if ($defaultEncryption.SSEAlgorithm -ne 'aws:kms' -or $defaultEncryption.KMSMasterKeyID -ne $ExpectedKmsKeyArn) {
        throw "Bucket '$Name' does not use the expected customer-managed KMS key."
    }
}

if ($Filename.Contains('..')) {
    throw 'Filename must not contain a parent-directory segment.'
}
if ($DestinationKey -and $DestinationKey.Contains('..')) {
    throw 'DestinationKey must not contain a parent-directory segment.'
}

$null = Get-Command -Name 'aws' -ErrorAction Stop
$null = Get-Command -Name 'curl.exe' -ErrorAction Stop

$expectedDigest = if ($ExpectedSha256) {
    $ExpectedSha256.ToLowerInvariant()
} else {
    Get-HuggingFaceFileDigest -ModelRepository $Repository -Commit $Revision -ModelFilename $Filename
}

$leafName = [IO.Path]::GetFileName($Filename)
$objectKey = if ($DestinationKey) {
    $DestinationKey
} else {
    "models/$($Repository.ToLowerInvariant())/$Revision/$leafName"
}

$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$workingDirectory = Join-Path $temporaryRoot "private-llm-chat-model-$([Guid]::NewGuid().ToString('N'))"
$downloadPath = Join-Path $workingDirectory $leafName

if (-not ([IO.Path]::GetFullPath($workingDirectory).StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase))) {
    throw 'Refusing to use a temporary directory outside the operating-system temporary root.'
}

New-Item -ItemType Directory -Path $workingDirectory | Out-Null

try {
    Assert-ModelBucketControls -Name $BucketName -ExpectedKmsKeyArn $KmsKeyArn

    $encodedPath = ($Filename.Split('/') | ForEach-Object { [Uri]::EscapeDataString($_) }) -join '/'
    $downloadUrl = "https://huggingface.co/$Repository/resolve/$Revision/$encodedPath`?download=true"
    Write-Host "Downloading immutable model revision $Revision from $Repository..."
    Invoke-NativeCommand -Command 'curl.exe' -Arguments @(
        '--fail', '--location', '--proto', '=https', '--tlsv1.2', '--retry', '3',
        '--output', $downloadPath, $downloadUrl
    )

    $actualDigest = (Get-FileHash -LiteralPath $downloadPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualDigest -ne $expectedDigest) {
        throw "Model checksum mismatch. Expected $expectedDigest but downloaded $actualDigest."
    }

    $destination = "s3://$BucketName/$objectKey"
    if ($PSCmdlet.ShouldProcess($destination, "Upload checksum-verified model '$leafName'")) {
        $metadata = "source-repository=$Repository,source-revision=$Revision,sha256=$actualDigest,ollama-model-name=$ModelName"
        Invoke-NativeCommand -Command 'aws' -Arguments @(
            's3', 'cp', $downloadPath, $destination,
            '--only-show-errors',
            '--sse', 'aws:kms',
            '--sse-kms-key-id', $KmsKeyArn,
            '--checksum-algorithm', 'SHA256',
            '--metadata', $metadata
        )

        # A large GGUF is normally uploaded in several parts. S3 can therefore
        # return a composite SHA-256 rather than the conventional whole-file
        # digest. The AWS CLI asks S3 to validate the transfer checksum above;
        # the whole-file digest is retained as metadata and checked again by
        # the Image Builder component after it downloads the object.
        $head = Invoke-NativeCommand -Command 'aws' -Arguments @(
            's3api', 'head-object', '--bucket', $BucketName, '--key', $objectKey,
            '--checksum-mode', 'ENABLED', '--output', 'json'
        ) | ConvertFrom-Json
        if ($head.Metadata.sha256 -ne $actualDigest -or $head.ContentLength -ne (Get-Item -LiteralPath $downloadPath).Length) {
            throw 'The uploaded S3 object metadata or size does not match the verified local model.'
        }

        Write-Output ''
        Write-Output '# Add these values to terraform.tfvars:'
        Write-Output "image_builder_model_s3_bucket = `"$BucketName`""
        Write-Output "image_builder_model_s3_key    = `"$objectKey`""
        Write-Output "image_builder_model_sha256    = `"$actualDigest`""
        Write-Output "image_builder_model_name      = `"$ModelName`""
    }
} finally {
    if ($KeepDownload) {
        Write-Host "Downloaded model retained at $downloadPath"
    } elseif (Test-Path -LiteralPath $workingDirectory) {
        $resolvedWorkingDirectory = [IO.Path]::GetFullPath($workingDirectory)
        if (-not $resolvedWorkingDirectory.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Refusing to remove a path outside the operating-system temporary root.'
        }
        Remove-Item -LiteralPath $resolvedWorkingDirectory -Recurse -Force
    }
}

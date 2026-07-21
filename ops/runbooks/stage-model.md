# Stage a model artefact

This procedure places one immutable GGUF model in the private, Terraform-managed
artefact bucket. It does not enable or start a GPU.

## Preconditions

- Review and accept the model licence for the intended use.
- Choose an official or otherwise approved Hugging Face repository.
- Resolve the source to a full 40-character commit SHA; do not use `main` or a
  mutable tag.
- Install the AWS CLI and authenticate with a short-lived identity that can read
  the bucket controls, encrypt with the project KMS key, and upload to the model
  bucket.
- Install `curl.exe`, which is included with current supported Windows versions.

## Create the landing bucket

Set `enable_model_artifact_bucket = true`, keep the Image Builder model values
unset, and apply the reviewed Terraform plan. Record these outputs:

- `model_artifact_bucket_name`
- `kms_key_arn`

The bucket is private, versioned and encrypted. Creating it does not download a
model or start chargeable GPU compute.

## Download, verify and upload

From the repository root, run:

```powershell
.\scripts\stage-model.ps1 `
  -Repository "Qwen/Qwen3-8B-GGUF" `
  -Revision "<full-40-character-commit-sha>" `
  -Filename "Qwen3-8B-Q4_K_M.gguf" `
  -BucketName "<model_artifact_bucket_name>" `
  -KmsKeyArn "<kms_key_arn>" `
  -ModelName "private"
```

The script retrieves the file's LFS SHA-256 from the pinned Hugging Face revision.
Use `-ExpectedSha256` when an independently published digest is available; the
download must match it. Before uploading, the script verifies S3 Block Public
Access, versioning and the expected KMS key. The AWS CLI asks S3 to validate an
upload checksum; the script then confirms the stored size and verified digest
metadata. The AMI build independently recalculates the whole-file SHA-256 after
downloading the object, so it never treats a multipart ETag as a content digest.

The script prints the four `image_builder_model_*` Terraform values. Add them to
the untracked `terraform.tfvars`, bump the immutable Image Builder component and
recipe versions when required, and follow the GPU AMI runbook.

Use `-WhatIf` to exercise discovery, download and checksum validation without an
S3 upload. Temporary downloads are removed by default; `-KeepDownload` retains
the file and prints its location.

# Model artefact storage

This module creates the private landing zone used before a model is baked into
an inference AMI. It deliberately stores model weights separately from encrypted
conversation data because the two data classes have different access and
retention requirements.

The bucket blocks public access, enforces bucket-owner object ownership, retains
superseded versions for recovery, and requires every upload to use the configured
customer-managed KMS key. `force_destroy` is disabled so removing the Terraform
module cannot silently delete staged model weights or their provenance records.

Use `scripts/stage-model.ps1` to place an immutable, checksum-verified Hugging
Face GGUF in this bucket. The Image Builder role is subsequently granted read
access to only the configured object key.

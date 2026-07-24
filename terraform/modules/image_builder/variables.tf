variable "name" {
  description = "Resource name prefix."
  type        = string
}

variable "aws_region" {
  description = "Region in which the private AMI is built."
  type        = string
}

variable "account_id" {
  description = "AWS account that owns the pipeline and approved AMI parameter."
  type        = string
}

variable "parent_image" {
  description = "Pinned AWS-owned GPU DLAMI ID."
  type        = string

  validation {
    condition     = can(regex("^ami-[0-9a-f]+$", var.parent_image))
    error_message = "parent_image must be a pinned AMI ID."
  }
}

variable "ollama_version" {
  description = "Pinned Ollama semantic version without the leading v."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+$", var.ollama_version))
    error_message = "ollama_version must be an exact semantic version such as 0.9.6."
  }
}

variable "ollama_sha256" {
  description = "SHA-256 digest for the pinned Ollama Linux amd64 tarball."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F]{64}$", var.ollama_sha256))
    error_message = "ollama_sha256 must be a 64-character hexadecimal SHA-256 digest."
  }
}

variable "component_version" {
  description = "AWSTOE component semantic version; bump whenever a component template changes."
  type        = string
  default     = "1.0.0"

  validation {
    condition     = can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+$", var.component_version))
    error_message = "component_version must be a three-part semantic version."
  }
}

variable "recipe_version" {
  description = "Image recipe semantic version; bump when inputs or components change."
  type        = string
  default     = "1.0.0"

  validation {
    condition     = can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+$", var.recipe_version))
    error_message = "recipe_version must be a three-part semantic version."
  }
}

variable "build_instance_types" {
  description = "GPU-capable instance types Image Builder may use, in preference order."
  type        = list(string)
  default     = ["g6.xlarge"]

  validation {
    condition     = length(var.build_instance_types) > 0
    error_message = "At least one GPU-capable build instance type is required."
  }
}

variable "build_availability_zone" {
  description = "Optional availability zone for the Image Builder subnet; use this to avoid a temporary zonal GPU-capacity shortage."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.build_availability_zone == null ||
      can(regex("^[a-z]{2}(-gov)?-[a-z]+-[0-9][a-z]$", var.build_availability_zone))
    )
    error_message = "build_availability_zone must be null or an availability zone such as eu-west-2a."
  }
}

variable "root_volume_gib" {
  description = "Encrypted root volume size for build, test, and resulting AMI."
  type        = number
  default     = 100

  validation {
    condition     = var.root_volume_gib >= 75
    error_message = "root_volume_gib must be at least 75 GiB, the current parent AMI snapshot size."
  }
}

variable "kms_key_arn" {
  description = "KMS key used to encrypt build logs and image EBS snapshots."
  type        = string
}

variable "model_s3_bucket" {
  description = "Optional S3 bucket containing a GGUF model artefact."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.model_s3_bucket == null || can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.model_s3_bucket))
    error_message = "model_s3_bucket must be null or a valid S3 bucket name."
  }
}

variable "model_s3_key" {
  description = "Optional S3 key for the GGUF model artefact."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.model_s3_key == null || can(regex("^[A-Za-z0-9._/-]+$", var.model_s3_key))
    error_message = "model_s3_key contains unsupported characters."
  }
}

variable "model_sha256" {
  description = "SHA-256 digest of the optional GGUF model."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.model_sha256 == null || can(regex("^[0-9a-fA-F]{64}$", var.model_sha256))
    error_message = "model_sha256 must be null or a 64-character hexadecimal digest."
  }
}

variable "model_name" {
  description = "Ollama name assigned to the imported GGUF model."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.model_name == null || can(regex("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", var.model_name))
    error_message = "model_name contains unsupported characters."
  }
}

variable "build_image_now" {
  description = "Trigger a tested image build during terraform apply. Usually false; run the pipeline explicitly in CI."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to supported Image Builder and EC2 resources."
  type        = map(string)
  default     = {}
}

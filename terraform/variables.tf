variable "aws_region" {
  description = "AWS region in which to create resources."
  type        = string
  default     = "eu-west-2"
}

variable "project_name" {
  description = "Short name used in resource names and tags."
  type        = string
  default     = "private-llm-chat"

  validation {
    condition     = can(regex("^[a-z0-9-]{3,32}$", var.project_name))
    error_message = "project_name must contain 3-32 lowercase letters, digits, or hyphens."
  }
}

variable "environment" {
  description = "Deployment environment identifier."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "owner" {
  description = "Person or team accountable for the resources and their AWS spend."
  type        = string

  validation {
    condition     = trimspace(var.owner) != "" && length(var.owner) <= 256
    error_message = "owner must contain a non-empty tag value no longer than 256 characters."
  }
}

variable "cost_center" {
  description = "Billing code or reporting bucket used for AWS cost allocation."
  type        = string

  validation {
    condition     = trimspace(var.cost_center) != "" && length(var.cost_center) <= 256
    error_message = "cost_center must contain a non-empty tag value no longer than 256 characters."
  }
}

variable "vpc_cidr" {
  description = "Private address range for the application VPC."
  type        = string
  default     = "10.42.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be a valid IPv4 CIDR."
  }
}

variable "conversation_retention_days" {
  description = "Days after which non-current encrypted conversation versions expire."
  type        = number
  default     = 90

  validation {
    condition     = var.conversation_retention_days >= 30
    error_message = "Retain non-current versions for at least 30 days."
  }
}

variable "enable_gpu" {
  description = "Create the private GPU inference host. Disabled by default to avoid cost."
  type        = bool
  default     = false
}

variable "enable_ssm_endpoints" {
  description = "Create private, hourly-billed Systems Manager endpoints. Enable for a session and disable afterwards to minimise personal-use cost."
  type        = bool
  default     = false
}

variable "ssm_endpoint_services" {
  description = "Systems Manager PrivateLink services required by the GPU's SSM Agent. Add ec2messages only for an older agent that requires it."
  type        = set(string)
  default     = ["ssm", "ssmmessages"]

  validation {
    condition     = contains(var.ssm_endpoint_services, "ssm") && contains(var.ssm_endpoint_services, "ssmmessages")
    error_message = "ssm_endpoint_services must include ssm and ssmmessages."
  }
}

variable "ssm_endpoint_subnet_count" {
  description = "Number of availability zones containing hourly-billed SSM endpoints. One is appropriate for personal use; two improves production availability."
  type        = number
  default     = 1

  validation {
    condition     = var.ssm_endpoint_subnet_count >= 1 && var.ssm_endpoint_subnet_count <= 2
    error_message = "ssm_endpoint_subnet_count must be one or two."
  }
}

variable "gpu_ami_id" {
  description = "ID of a hardened, pre-baked AMI containing the NVIDIA driver and inference server. Required when enable_gpu is true."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.gpu_ami_id == null || can(regex("^ami-[0-9a-f]+$", var.gpu_ami_id))
    error_message = "gpu_ami_id must be null or a valid AMI ID."
  }
}

variable "gpu_ami_ssm_parameter_name" {
  description = "Optional Image Builder output parameter to resolve as the approved runtime AMI. The parameter must already exist."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.gpu_ami_ssm_parameter_name == null || can(regex("^/[A-Za-z0-9_./-]+$", var.gpu_ami_ssm_parameter_name))
    error_message = "gpu_ami_ssm_parameter_name must be null or an absolute SSM parameter path."
  }
}

variable "enable_image_builder" {
  description = "Create an EC2 Image Builder pipeline for the private inference AMI. Disabled by default."
  type        = bool
  default     = false
}

variable "build_image_now" {
  description = "Start a chargeable GPU image build during terraform apply. Prefer explicit pipeline execution in CI."
  type        = bool
  default     = false

  validation {
    condition     = !var.build_image_now || var.enable_image_builder
    error_message = "build_image_now requires enable_image_builder to be true."
  }
}

variable "image_builder_parent_image" {
  description = "Pinned AWS-owned GPU DLAMI ID; required when Image Builder is enabled."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      !var.enable_image_builder ||
      (var.image_builder_parent_image != null && can(regex("^ami-[0-9a-f]+$", var.image_builder_parent_image)))
    )
    error_message = "Set image_builder_parent_image to a pinned AWS GPU DLAMI when Image Builder is enabled."
  }
}

variable "ollama_version" {
  description = "Exact Ollama semantic version installed into the AMI. Required when Image Builder is enabled."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = !var.enable_image_builder || (var.ollama_version != null && can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+$", var.ollama_version)))
    error_message = "Set ollama_version to an exact three-part version when Image Builder is enabled."
  }
}

variable "ollama_sha256" {
  description = "SHA-256 digest for the pinned Ollama Linux amd64 tarball. Required when Image Builder is enabled."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = !var.enable_image_builder || (var.ollama_sha256 != null && can(regex("^[0-9a-fA-F]{64}$", var.ollama_sha256)))
    error_message = "Set ollama_sha256 to the verified release digest when Image Builder is enabled."
  }
}

variable "image_builder_component_version" {
  description = "AWSTOE component version. Bump whenever component templates change."
  type        = string
  default     = "1.0.5"
}

variable "image_builder_recipe_version" {
  description = "Image recipe version. Bump whenever recipe inputs change."
  type        = string
  default     = "1.0.5"
}

variable "image_builder_instance_types" {
  description = "Compatible GPU instance types Image Builder may select by available capacity, in preference order."
  type        = list(string)
  default     = ["g6.xlarge", "g5.xlarge", "g4dn.xlarge"]
}

variable "image_builder_availability_zone" {
  description = "Optional availability zone for temporary Image Builder instances."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.image_builder_availability_zone == null ||
      startswith(var.image_builder_availability_zone, "${var.aws_region}") &&
      can(regex("^[a-z]{2}(-gov)?-[a-z]+-[0-9][a-z]$", var.image_builder_availability_zone))
    )
    error_message = "image_builder_availability_zone must belong to aws_region, for example eu-west-2a."
  }
}

variable "enable_model_artifact_bucket" {
  description = "Create a private, versioned, KMS-encrypted bucket for verified model files. Disabled by default to avoid storage cost."
  type        = bool
  default     = false
}

variable "model_artifact_noncurrent_retention_days" {
  description = "Days to retain older versions of staged model files before S3 removes them."
  type        = number
  default     = 90

  validation {
    condition     = var.model_artifact_noncurrent_retention_days >= 30
    error_message = "Retain non-current model versions for at least 30 days."
  }
}

variable "image_builder_model_s3_bucket" {
  description = "Optional existing bucket containing a private GGUF model artefact. Leave null to use the managed model bucket."
  type        = string
  default     = null
  nullable    = true
}

variable "image_builder_model_s3_key" {
  description = "Optional key for the private GGUF model artefact."
  type        = string
  default     = null
  nullable    = true
}

variable "image_builder_model_sha256" {
  description = "SHA-256 digest for the optional model artefact."
  type        = string
  default     = null
  nullable    = true
}

variable "image_builder_model_name" {
  description = "Ollama name assigned to the optional imported model."
  type        = string
  default     = null
  nullable    = true
}

variable "gpu_instance_type" {
  description = "EC2 instance type for private inference."
  type        = string
  default     = "g6.xlarge"
}

variable "gpu_root_volume_gib" {
  description = "Encrypted root volume size, including room for model weights."
  type        = number
  default     = 100

  validation {
    condition     = var.gpu_root_volume_gib >= 75
    error_message = "gpu_root_volume_gib must be at least 75 GiB, the current parent AMI snapshot size."
  }
}

variable "gpu_max_runtime_minutes" {
  description = "Hard instance-side safety limit after each GPU boot, even if the controlling laptop disconnects."
  type        = number
  default     = 120

  validation {
    condition     = var.gpu_max_runtime_minutes >= 15 && var.gpu_max_runtime_minutes <= 720
    error_message = "gpu_max_runtime_minutes must be between 15 and 720 minutes."
  }
}

variable "model_port" {
  description = "Private inference server port. It is never opened publicly."
  type        = number
  default     = 11434

  validation {
    condition     = var.model_port >= 1024 && var.model_port <= 65535
    error_message = "model_port must be between 1024 and 65535."
  }
}

variable "tags" {
  description = "Additional cost/reporting tags applied to supported resources. Reserved standard keys cannot be overridden."
  type        = map(string)
  default     = {}

  validation {
    condition = length(setintersection(
      toset(keys(var.tags)),
      toset(["Project", "Environment", "ManagedBy", "Owner", "CostCenter", "Repository"])
    )) == 0
    error_message = "tags must not override Project, Environment, ManagedBy, Owner, CostCenter, or Repository."
  }
}

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

variable "gpu_instance_type" {
  description = "EC2 instance type for private inference."
  type        = string
  default     = "g6.xlarge"
}

variable "gpu_root_volume_gib" {
  description = "Encrypted root volume size, including room for model weights."
  type        = number
  default     = 200

  validation {
    condition     = var.gpu_root_volume_gib >= 50
    error_message = "gpu_root_volume_gib must be at least 50 GiB."
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
  description = "Additional tags applied to all resources. Do not put secrets in tags."
  type        = map(string)
  default     = {}
}


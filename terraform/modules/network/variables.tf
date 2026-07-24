variable "name" {
  type        = string
  description = "Resource name prefix."
}

variable "vpc_cidr" {
  type        = string
  description = "VPC IPv4 CIDR."
}

variable "aws_region" {
  type        = string
  description = "Region used to form VPC endpoint service names."
}

variable "enable_ssm_endpoints" {
  type        = bool
  description = "Create hourly-billed private endpoints used for GPU management sessions."
  default     = false
}

variable "ssm_endpoint_services" {
  type        = set(string)
  description = "Systems Manager endpoint services required by the selected SSM Agent."
  default     = ["ssm", "ssmmessages"]

  validation {
    condition     = contains(var.ssm_endpoint_services, "ssm") && contains(var.ssm_endpoint_services, "ssmmessages")
    error_message = "ssm_endpoint_services must include ssm and ssmmessages."
  }
}

variable "ssm_endpoint_subnet_count" {
  type        = number
  description = "Availability-zone count for SSM endpoints; one minimises personal-use hourly cost."
  default     = 1

  validation {
    condition     = var.ssm_endpoint_subnet_count >= 1 && var.ssm_endpoint_subnet_count <= 2
    error_message = "ssm_endpoint_subnet_count must be one or two."
  }
}

variable "name" {
  type        = string
  description = "Resource name prefix."
}

variable "bucket_arn" {
  type        = string
  description = "Conversation bucket ARN."
}

variable "kms_key_arn" {
  type        = string
  description = "Conversation encryption key ARN."
}

variable "gpu_instance_arn" {
  type        = string
  description = "Optional inference instance ARN."
  default     = null
  nullable    = true
}

variable "enable_gpu_control" {
  type        = bool
  description = "Whether to create the GPU control policy. This must be a plan-time value rather than being inferred from the instance ARN."
  default     = false
}

variable "aws_region" {
  type        = string
  description = "Region containing the private GPU and SSM documents."
}

variable "account_id" {
  type        = string
  description = "AWS account used to scope controllable Session Manager sessions."
}

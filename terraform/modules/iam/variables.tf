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


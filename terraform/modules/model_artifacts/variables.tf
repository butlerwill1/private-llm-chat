variable "name" {
  description = "Resource name prefix."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key used for server-side encryption of model artefacts."
  type        = string
}

variable "noncurrent_retention_days" {
  description = "Days to retain superseded model-object versions."
  type        = number
  default     = 90

  validation {
    condition     = var.noncurrent_retention_days >= 30
    error_message = "Model artefact versions must be retained for at least 30 days."
  }
}

variable "tags" {
  description = "Standard cost-allocation tags applied to model artefact resources."
  type        = map(string)
  default     = {}
}

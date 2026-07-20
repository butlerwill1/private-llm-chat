variable "name" {
  type        = string
  description = "Resource name prefix."
}

variable "account_id" {
  type        = string
  description = "AWS account that administers the KMS key."
}

variable "conversation_retention_days" {
  type        = number
  description = "Retention for non-current object versions."
}


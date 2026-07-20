output "conversation_bucket_name" {
  description = "Encrypted conversation storage bucket."
  value       = module.data.bucket_name
}

output "kms_key_arn" {
  description = "KMS key used for conversation and GPU EBS encryption."
  value       = module.data.kms_key_arn
}

output "application_data_policy_arn" {
  description = "Policy to attach to the application runtime role."
  value       = module.iam.application_data_policy_arn
}

output "gpu_control_policy_arn" {
  description = "Start/stop policy for the optional tagged GPU host; null when disabled."
  value       = module.iam.gpu_control_policy_arn
}

output "gpu_private_ip" {
  description = "Private GPU address, or null when GPU creation is disabled."
  value       = var.enable_gpu ? module.gpu[0].private_ip : null
}

output "application_security_group_id" {
  description = "Attach this security group to application compute that calls the GPU."
  value       = module.network.application_security_group_id
}

output "cost_allocation_tags" {
  description = "Protected tags applied to all AWS resources that support tagging."
  value       = local.common_tags
}

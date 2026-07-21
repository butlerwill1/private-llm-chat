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

output "gpu_instance_id" {
  description = "Private GPU instance ID used by the personal session script, or null when disabled."
  value       = var.enable_gpu ? module.gpu[0].instance_id : null
}

output "application_security_group_id" {
  description = "Attach this security group to application compute that calls the GPU."
  value       = module.network.application_security_group_id
}

output "image_builder_pipeline_arn" {
  description = "Manual GPU AMI pipeline ARN, or null when Image Builder is disabled."
  value       = var.enable_image_builder ? module.image_builder[0].pipeline_arn : null
}

output "approved_gpu_ami_id" {
  description = "AMI produced by an opt-in Terraform-managed build, or an explicitly supplied approved AMI."
  value       = local.selected_gpu_ami_id
}

output "approved_gpu_ami_parameter_name" {
  description = "Parameter Image Builder updates after successful tests and distribution."
  value       = var.enable_image_builder ? module.image_builder[0].approved_ami_parameter_name : null
}

output "model_artifact_bucket_name" {
  description = "Private bucket used to stage verified model files, or null when its creation is disabled."
  value       = try(module.model_artifacts[0].bucket_name, null)
}

output "model_artifact_bucket_arn" {
  description = "ARN of the managed model artefact bucket, or null when its creation is disabled."
  value       = try(module.model_artifacts[0].bucket_arn, null)
}

output "cost_allocation_tags" {
  description = "Protected tags applied to all AWS resources that support tagging."
  value       = local.common_tags
}

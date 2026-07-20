output "application_data_policy_arn" {
  value       = aws_iam_policy.application_data.arn
  description = "Application data-access policy ARN."
}

output "gpu_control_policy_arn" {
  value       = try(aws_iam_policy.gpu_control[0].arn, null)
  description = "GPU lifecycle policy ARN, or null when no GPU exists."
}


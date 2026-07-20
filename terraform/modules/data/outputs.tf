output "bucket_name" {
  value       = aws_s3_bucket.conversation.id
  description = "Conversation bucket name."
}

output "bucket_arn" {
  value       = aws_s3_bucket.conversation.arn
  description = "Conversation bucket ARN."
}

output "kms_key_arn" {
  value       = aws_kms_key.conversation.arn
  description = "Conversation KMS key ARN."
}


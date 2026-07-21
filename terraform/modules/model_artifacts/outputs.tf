output "bucket_name" {
  description = "Private bucket into which approved model artefacts are staged."
  value       = aws_s3_bucket.models.id
}

output "bucket_arn" {
  description = "ARN of the private model artefact bucket."
  value       = aws_s3_bucket.models.arn
}

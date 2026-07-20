output "vpc_id" {
  value       = aws_vpc.this.id
  description = "VPC ID."
}

output "private_subnet_ids" {
  value       = values(aws_subnet.private)[*].id
  description = "Isolated private subnet IDs."
}

output "application_security_group_id" {
  value       = aws_security_group.application.id
  description = "Security group identifying application callers."
}

output "s3_prefix_list_id" {
  value       = aws_vpc_endpoint.s3.prefix_list_id
  description = "AWS-managed S3 prefix list used for restricted egress."
}

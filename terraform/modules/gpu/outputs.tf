output "private_ip" {
  value       = aws_instance.gpu.private_ip
  description = "Private inference host IP address."
}

output "instance_arn" {
  value       = aws_instance.gpu.arn
  description = "Inference instance ARN."
}

output "instance_id" {
  value       = aws_instance.gpu.id
  description = "Inference instance ID used by EC2 and Systems Manager commands."
}

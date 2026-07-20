output "private_ip" {
  value       = aws_instance.gpu.private_ip
  description = "Private inference host IP address."
}

output "instance_arn" {
  value       = aws_instance.gpu.arn
  description = "Inference instance ARN."
}


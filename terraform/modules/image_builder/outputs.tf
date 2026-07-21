output "pipeline_arn" {
  description = "ARN to pass to start-image-pipeline-execution after review."
  value       = aws_imagebuilder_image_pipeline.gpu.arn
}

output "recipe_arn" {
  description = "Pinned image recipe ARN."
  value       = aws_imagebuilder_image_recipe.gpu.arn
}

output "approved_ami_id" {
  description = "AMI that passed build and test phases when build_image_now is enabled; otherwise null."
  value       = try(flatten(aws_imagebuilder_image.approved[*].output_resources[*].amis)[0].image, null)
}

output "build_log_bucket_name" {
  description = "Encrypted bucket containing Image Builder execution logs."
  value       = aws_s3_bucket.logs.id
}

output "approved_ami_parameter_name" {
  description = "SSM aws:ec2:image parameter updated only after successful distribution."
  value       = local.approved_ami_parameter_name
}

resource "aws_iam_policy" "application_data" {
  name        = "${var.name}-application-data"
  description = "Read and write encrypted private LLM conversation data"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ListConversationPrefix"
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:ListBucketVersions"]
        Resource = var.bucket_arn
        Condition = {
          StringLike = { "s3:prefix" = ["conversations/*"] }
        }
      },
      {
        Sid    = "ManageConversationObjects"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:DeleteObjectVersion"
        ]
        Resource = "${var.bucket_arn}/conversations/*"
      },
      {
        Sid      = "UseConversationKey"
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
        Resource = var.kms_key_arn
      }
    ]
  })
}

# GPU control belongs on a dedicated control-plane role, not every request handler.
resource "aws_iam_policy" "gpu_control" {
  count = var.gpu_instance_arn == null ? 0 : 1

  name        = "${var.name}-gpu-control"
  description = "Start and stop only the private inference instance"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "StartStopInferenceHost"
        Effect   = "Allow"
        Action   = ["ec2:StartInstances", "ec2:StopInstances"]
        Resource = var.gpu_instance_arn
        Condition = {
          StringEquals = { "ec2:ResourceTag/ControlScope" = var.name }
        }
      },
      {
        Sid      = "DescribeForReadinessChecks"
        Effect   = "Allow"
        Action   = ["ec2:DescribeInstances", "ec2:DescribeInstanceStatus"]
        Resource = "*"
      }
    ]
  })
}

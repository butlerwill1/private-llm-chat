data "aws_partition" "current" {}

resource "aws_kms_key" "conversation" {
  description             = "Envelope encryption for private LLM chat data"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AccountAdministration"
      Effect    = "Allow"
      Principal = { AWS = "arn:${data.aws_partition.current.partition}:iam::${var.account_id}:root" }
      Action    = "kms:*"
      Resource  = "*"
    }]
  })
}

resource "aws_kms_alias" "conversation" {
  name          = "alias/${var.name}-conversation"
  target_key_id = aws_kms_key.conversation.key_id
}

resource "aws_s3_bucket" "conversation" {
  bucket_prefix = "${var.name}-conversation-"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "conversation" {
  bucket = aws_s3_bucket.conversation.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "conversation" {
  bucket = aws_s3_bucket.conversation.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "conversation" {
  bucket = aws_s3_bucket.conversation.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "conversation" {
  bucket = aws_s3_bucket.conversation.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.conversation.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "conversation" {
  bucket = aws_s3_bucket.conversation.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.conversation_retention_days
    }
  }

  depends_on = [aws_s3_bucket_versioning.conversation]
}

resource "aws_s3_bucket_policy" "conversation" {
  bucket = aws_s3_bucket.conversation.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.conversation.arn, "${aws_s3_bucket.conversation.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
      {
        Sid       = "DenyUnencryptedObjectUploads"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.conversation.arn}/*"
        Condition = { StringNotEquals = { "s3:x-amz-server-side-encryption" = "aws:kms" } }
      }
    ]
  })
}


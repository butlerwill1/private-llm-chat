locals {
  s3_model_enabled            = var.model_s3_bucket != null
  registry_model_enabled      = var.ollama_model_reference != null
  model_enabled               = local.s3_model_enabled || local.registry_model_enabled
  model_source                = local.s3_model_enabled ? "s3_gguf" : (local.registry_model_enabled ? "ollama_registry" : "none")
  ollama_url                  = "https://github.com/ollama/ollama/releases/download/v${var.ollama_version}/ollama-linux-amd64.tar.zst"
  approved_ami_parameter_name = "/${var.name}/gpu/approved-ami"
}

data "aws_partition" "current" {}

# An explicit ID prevents base-image drift; the owner filter rejects private or
# third-party images. The GPU/NVIDIA component test rejects a non-GPU AWS image.
data "aws_ami" "parent" {
  most_recent = false
  owners      = ["amazon"]

  filter {
    name   = "image-id"
    values = [var.parent_image]
  }
}

resource "terraform_data" "validate_model_inputs" {
  lifecycle {
    precondition {
      condition = (
        (
          var.model_s3_bucket == null && var.model_s3_key == null && var.model_sha256 == null &&
          var.ollama_model_reference == null && var.ollama_model_manifest_digest == null && var.model_name == null
        ) ||
        (
          var.model_s3_bucket != null && var.model_s3_key != null && var.model_sha256 != null &&
          var.ollama_model_reference == null && var.ollama_model_manifest_digest == null && var.model_name != null
        ) ||
        (
          var.model_s3_bucket == null && var.model_s3_key == null && var.model_sha256 == null &&
          var.ollama_model_reference != null && var.ollama_model_manifest_digest != null && var.model_name != null
        )
      )
      error_message = "Choose exactly one model source: complete S3 GGUF fields or a complete pinned Ollama registry reference and digest."
    }
  }
}

# Image construction is isolated from the runtime VPC. The temporary build/test
# instances need HTTPS egress for the pinned Ollama release, but accept no ingress.
resource "aws_vpc" "build" {
  cidr_block           = "10.253.0.0/24"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, { Name = "${var.name}-image-build" })
}

resource "aws_internet_gateway" "build" {
  vpc_id = aws_vpc.build.id
  tags   = merge(var.tags, { Name = "${var.name}-image-build" })
}

resource "aws_subnet" "build" {
  vpc_id     = aws_vpc.build.id
  cidr_block = "10.253.0.0/25"
  # Pinning is optional because zonal GPU capacity can vary. A deployment may
  # select another AZ without changing the build VPC's address plan.
  availability_zone       = var.build_availability_zone
  map_public_ip_on_launch = true

  tags = merge(var.tags, { Name = "${var.name}-image-build" })
}

resource "aws_route_table" "build" {
  vpc_id = aws_vpc.build.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.build.id
  }

  tags = merge(var.tags, { Name = "${var.name}-image-build" })
}

resource "aws_route_table_association" "build" {
  subnet_id      = aws_subnet.build.id
  route_table_id = aws_route_table.build.id
}

resource "aws_security_group" "build" {
  name_prefix = "${var.name}-image-build-"
  description = "No ingress; HTTPS-only egress for ephemeral Image Builder instances"
  vpc_id      = aws_vpc.build.id

  egress {
    description = "Fetch pinned release and reach AWS APIs"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "DNS to VPC resolver"
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = ["${cidrhost(aws_vpc.build.cidr_block, 2)}/32"]
  }

  egress {
    description = "DNS over TCP to VPC resolver"
    from_port   = 53
    to_port     = 53
    protocol    = "tcp"
    cidr_blocks = ["${cidrhost(aws_vpc.build.cidr_block, 2)}/32"]
  }

  tags = var.tags

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_s3_bucket" "logs" {
  # S3 reserves room for Terraform's generated suffix, so bucket_prefix must be
  # no longer than 37 characters. "ib" keeps the purpose clear within that limit.
  bucket_prefix = "${var.name}-ib-logs-"
  force_destroy = false
  tags          = var.tags
}

resource "aws_s3_bucket_public_access_block" "logs" {
  bucket = aws_s3_bucket.logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = var.kms_key_arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_versioning" "logs" {
  bucket = aws_s3_bucket.logs.id

  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    id     = "expire-build-logs"
    status = "Enabled"
    filter {}

    expiration { days = 30 }
    noncurrent_version_expiration { noncurrent_days = 30 }
  }


  depends_on = [aws_s3_bucket_versioning.logs]
}

data "aws_iam_policy_document" "logs_bucket" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.logs.arn, "${aws_s3_bucket.logs.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "logs" {
  bucket = aws_s3_bucket.logs.id
  policy = data.aws_iam_policy_document.logs_bucket.json
}

data "aws_iam_policy_document" "assume_ec2" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "builder" {
  name               = "${var.name}-image-builder"
  assume_role_policy = data.aws_iam_policy_document.assume_ec2.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "image_builder" {
  role       = aws_iam_role.builder.name
  policy_arn = "arn:aws:iam::aws:policy/EC2InstanceProfileForImageBuilder"
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.builder.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "builder_data" {
  statement {
    sid       = "WriteBuildLogs"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.logs.arn}/image-builder/*"]
  }

  statement {
    sid       = "UseBuildEncryptionKey"
    actions   = ["kms:Decrypt", "kms:DescribeKey", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = [var.kms_key_arn]
  }

  dynamic "statement" {
    for_each = local.s3_model_enabled ? [1] : []
    content {
      sid       = "ReadChecksumVerifiedModel"
      actions   = ["s3:GetObject"]
      resources = ["arn:aws:s3:::${var.model_s3_bucket}/${var.model_s3_key}"]
    }
  }
}

resource "aws_iam_role_policy" "builder_data" {
  name   = "${var.name}-image-builder-data"
  role   = aws_iam_role.builder.id
  policy = data.aws_iam_policy_document.builder_data.json
}

resource "aws_iam_instance_profile" "builder" {
  name = "${var.name}-image-builder"
  role = aws_iam_role.builder.name
  tags = var.tags
}

data "aws_iam_policy_document" "assume_image_builder" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["imagebuilder.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name}-image-builder-execution"
  assume_role_policy = data.aws_iam_policy_document.assume_image_builder.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/EC2ImageBuilderExecutionPolicy"
}

data "aws_iam_policy_document" "publish_approved_ami" {
  statement {
    sid       = "PublishApprovedAmiId"
    actions   = ["ssm:PutParameter"]
    resources = ["arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}:${var.account_id}:parameter${local.approved_ami_parameter_name}"]
  }

  statement {
    sid       = "ValidateAmiIdParameter"
    actions   = ["ec2:DescribeImages"]
    resources = ["*"]
  }

  statement {
    sid = "UseImageEncryptionKey"
    actions = [
      "kms:CreateGrant",
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKeyWithoutPlaintext",
      "kms:ReEncryptFrom",
      "kms:ReEncryptTo"
    ]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "publish_approved_ami" {
  name   = "${var.name}-publish-approved-ami"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.publish_approved_ami.json
}

resource "aws_imagebuilder_component" "install" {
  name        = "${var.name}-install-ollama"
  description = "Install checksum-verified Ollama and optionally import a verified GGUF model"
  platform    = "Linux"
  version     = var.component_version
  tags        = var.tags

  data = templatefile("${path.module}/components/install-ollama.yaml.tftpl", {
    model_enabled                  = local.model_enabled ? "true" : "false"
    model_source                   = local.model_source
    model_name                     = coalesce(var.model_name, "not-configured")
    model_s3_uri                   = local.s3_model_enabled ? "s3://${var.model_s3_bucket}/${var.model_s3_key}" : "not-configured"
    model_sha256                   = coalesce(var.model_sha256, "not-configured")
    registry_model_reference       = coalesce(var.ollama_model_reference, "not-configured")
    registry_model_manifest_digest = coalesce(var.ollama_model_manifest_digest, "not-configured")
    ollama_sha256                  = lower(var.ollama_sha256)
    ollama_url                     = local.ollama_url
    ollama_version                 = var.ollama_version
    readiness_script_base64        = filebase64("${path.module}/scripts/verify-ollama-readiness.sh")
  })

  depends_on = [terraform_data.validate_model_inputs]
}

resource "aws_imagebuilder_component" "test" {
  name        = "${var.name}-test-ollama"
  description = "Test NVIDIA, Ollama, optional model import, and GPU-backed inference"
  platform    = "Linux"
  version     = var.component_version
  tags        = var.tags

  data = templatefile("${path.module}/components/test-ollama.yaml.tftpl", {
    model_enabled  = local.model_enabled ? "true" : "false"
    model_name     = coalesce(var.model_name, "not-configured")
    ollama_version = var.ollama_version
  })
}

resource "aws_imagebuilder_image_recipe" "gpu" {
  name         = "${var.name}-gpu"
  description  = "Private GPU inference AMI based on an approved AWS GPU DLAMI"
  parent_image = data.aws_ami.parent.id
  version      = var.recipe_version
  tags         = var.tags
  component { component_arn = aws_imagebuilder_component.install.arn }
  component { component_arn = aws_imagebuilder_component.test.arn }

  block_device_mapping {
    device_name = "/dev/sda1"
    ebs {
      delete_on_termination = true
      encrypted             = true
      kms_key_id            = var.kms_key_arn
      volume_size           = var.root_volume_gib
      volume_type           = "gp3"
    }
  }

  systems_manager_agent { uninstall_after_build = false }
}

resource "aws_imagebuilder_infrastructure_configuration" "gpu" {
  name                          = "${var.name}-gpu"
  description                   = "Ephemeral GPU build hosts with no inbound network access"
  instance_profile_name         = aws_iam_instance_profile.builder.name
  instance_types                = var.build_instance_types
  subnet_id                     = aws_subnet.build.id
  security_group_ids            = [aws_security_group.build.id]
  terminate_instance_on_failure = true
  resource_tags                 = merge(var.tags, { Purpose = "ephemeral-image-build" })
  tags                          = var.tags

  instance_metadata_options {
    http_put_response_hop_limit = 1
    http_tokens                 = "required"
  }

  logging {
    s3_logs {
      s3_bucket_name = aws_s3_bucket.logs.id
      s3_key_prefix  = "image-builder"
    }
  }
}

resource "aws_imagebuilder_distribution_configuration" "gpu" {
  name        = "${var.name}-gpu"
  description = "Keep tested inference AMIs private in the build account"
  tags        = var.tags

  distribution {
    region = var.aws_region
    ami_distribution_configuration {
      name        = "${var.name}-gpu-{{ imagebuilder:buildDate }}"
      description = "Private Ollama GPU image candidate; approval requires the SSM parameter"
      # Image Builder creates the AMI before its test phase. Calling it approved
      # here would leave a misleading tag on an AMI whose tests later fail.
      ami_tags = merge(var.tags, {
        ImageStatus = "candidate"
        Role        = "private-inference"
      })
    }

    ssm_parameter_configuration {
      parameter_name = local.approved_ami_parameter_name
      data_type      = "aws:ec2:image"
    }
  }
}

resource "aws_imagebuilder_image_pipeline" "gpu" {
  name                             = "${var.name}-gpu"
  description                      = "Manually triggered, tested private GPU inference image pipeline"
  image_recipe_arn                 = aws_imagebuilder_image_recipe.gpu.arn
  infrastructure_configuration_arn = aws_imagebuilder_infrastructure_configuration.gpu.arn
  distribution_configuration_arn   = aws_imagebuilder_distribution_configuration.gpu.arn
  execution_role                   = aws_iam_role.execution.arn
  status                           = "ENABLED"
  tags                             = var.tags

  image_tests_configuration {
    image_tests_enabled = true
    timeout_minutes     = 90
  }

  lifecycle {
    replace_triggered_by = [aws_imagebuilder_image_recipe.gpu]
  }
}

# Opt-in because this resource starts chargeable GPU build and test instances.
resource "aws_imagebuilder_image" "approved" {
  count = var.build_image_now ? 1 : 0

  image_recipe_arn                 = aws_imagebuilder_image_recipe.gpu.arn
  infrastructure_configuration_arn = aws_imagebuilder_infrastructure_configuration.gpu.arn
  distribution_configuration_arn   = aws_imagebuilder_distribution_configuration.gpu.arn
  execution_role                   = aws_iam_role.execution.arn
  enhanced_image_metadata_enabled  = true

  image_tests_configuration {
    image_tests_enabled = true
    timeout_minutes     = 90
  }
}

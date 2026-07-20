locals {
  name = "${var.project_name}-${var.environment}"

  # These protected tags form the shared cost-allocation vocabulary used by the
  # neighbouring projects. Custom tags may add dimensions but cannot replace them.
  common_tags = merge(var.tags, {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Owner       = var.owner
    CostCenter  = var.cost_center
    Repository  = "butlerwill1/private-llm-chat"
  })
}

data "aws_caller_identity" "current" {}

module "network" {
  source = "./modules/network"

  name       = local.name
  vpc_cidr   = var.vpc_cidr
  aws_region = var.aws_region
}

module "data" {
  source = "./modules/data"

  name                        = local.name
  account_id                  = data.aws_caller_identity.current.account_id
  conversation_retention_days = var.conversation_retention_days
}

module "iam" {
  source = "./modules/iam"

  name             = local.name
  bucket_arn       = module.data.bucket_arn
  kms_key_arn      = module.data.kms_key_arn
  gpu_instance_arn = var.enable_gpu ? module.gpu[0].instance_arn : null
}

module "gpu" {
  count  = var.enable_gpu ? 1 : 0
  source = "./modules/gpu"

  name              = local.name
  ami_id            = var.gpu_ami_id
  instance_type     = var.gpu_instance_type
  root_volume_gib   = var.gpu_root_volume_gib
  kms_key_arn       = module.data.kms_key_arn
  subnet_id         = module.network.private_subnet_ids[0]
  vpc_id            = module.network.vpc_id
  vpc_cidr          = var.vpc_cidr
  s3_prefix_list_id = module.network.s3_prefix_list_id
  application_sg_id = module.network.application_security_group_id
  model_port        = var.model_port
  tags              = local.common_tags
}

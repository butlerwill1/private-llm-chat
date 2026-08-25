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

  selected_gpu_ami_id = var.gpu_ami_id != null ? var.gpu_ami_id : (
    var.gpu_ami_ssm_parameter_name != null ? nonsensitive(data.aws_ssm_parameter.approved_gpu_ami[0].value) :
    try(module.image_builder[0].approved_ami_id, null)
  )

  # An existing bucket may still be supplied for teams that already operate a
  # controlled artefact store. Otherwise, the optional managed bucket below is
  # the safe default used by the model staging script.
  managed_model_artifact_bucket_name = try(module.model_artifacts[0].bucket_name, null)
  selected_model_artifact_bucket_name = var.image_builder_model_s3_bucket != null ? (
    var.image_builder_model_s3_bucket
  ) : local.managed_model_artifact_bucket_name
}

check "model_artifact_configuration" {
  assert {
    condition = (
      (
        var.image_builder_model_s3_key == null &&
        var.image_builder_model_sha256 == null &&
        var.image_builder_ollama_model_reference == null &&
        var.image_builder_ollama_model_manifest_digest == null &&
        var.image_builder_model_name == null
      ) ||
      (
        local.selected_model_artifact_bucket_name != null &&
        var.image_builder_model_s3_key != null &&
        var.image_builder_model_sha256 != null &&
        var.image_builder_model_name != null &&
        var.image_builder_ollama_model_reference == null &&
        var.image_builder_ollama_model_manifest_digest == null
      ) ||
      (
        var.image_builder_model_s3_key == null &&
        var.image_builder_model_sha256 == null &&
        var.image_builder_model_name != null &&
        var.image_builder_ollama_model_reference != null &&
        var.image_builder_ollama_model_manifest_digest != null
      )
    )
    error_message = "Choose exactly one model source: a verified S3 GGUF or a digest-pinned Ollama registry model. Set its complete source fields and model name together."
  }
}

data "aws_caller_identity" "current" {}

data "aws_ssm_parameter" "approved_gpu_ami" {
  count = var.gpu_ami_id != null || var.gpu_ami_ssm_parameter_name == null ? 0 : 1
  name  = var.gpu_ami_ssm_parameter_name
}

module "network" {
  source = "./modules/network"

  name                      = local.name
  vpc_cidr                  = var.vpc_cidr
  aws_region                = var.aws_region
  enable_ssm_endpoints      = var.enable_ssm_endpoints
  ssm_endpoint_services     = var.ssm_endpoint_services
  ssm_endpoint_subnet_count = var.ssm_endpoint_subnet_count
}

module "data" {
  source = "./modules/data"

  name                        = local.name
  account_id                  = data.aws_caller_identity.current.account_id
  conversation_retention_days = var.conversation_retention_days
}

module "model_artifacts" {
  count  = var.enable_model_artifact_bucket ? 1 : 0
  source = "./modules/model_artifacts"

  name                      = local.name
  kms_key_arn               = module.data.kms_key_arn
  noncurrent_retention_days = var.model_artifact_noncurrent_retention_days
  tags                      = local.common_tags
}

module "iam" {
  source = "./modules/iam"

  name               = local.name
  bucket_arn         = module.data.bucket_arn
  kms_key_arn        = module.data.kms_key_arn
  enable_gpu_control = var.enable_gpu
  gpu_instance_arn   = var.enable_gpu ? module.gpu[0].instance_arn : null
  aws_region         = var.aws_region
  account_id         = data.aws_caller_identity.current.account_id
}

module "image_builder" {
  count  = var.enable_image_builder ? 1 : 0
  source = "./modules/image_builder"

  name                         = local.name
  aws_region                   = var.aws_region
  account_id                   = data.aws_caller_identity.current.account_id
  parent_image                 = coalesce(var.image_builder_parent_image, "ami-00000000000000000")
  ollama_version               = coalesce(var.ollama_version, "0.0.0")
  ollama_sha256                = coalesce(var.ollama_sha256, "0000000000000000000000000000000000000000000000000000000000000000")
  component_version            = var.image_builder_component_version
  recipe_version               = var.image_builder_recipe_version
  build_instance_types         = var.image_builder_instance_types
  build_availability_zone      = var.image_builder_availability_zone
  root_volume_gib              = var.gpu_root_volume_gib
  kms_key_arn                  = module.data.kms_key_arn
  model_s3_bucket              = var.image_builder_model_s3_key == null ? null : local.selected_model_artifact_bucket_name
  model_s3_key                 = var.image_builder_model_s3_key
  model_sha256                 = var.image_builder_model_sha256
  model_name                   = var.image_builder_model_name
  ollama_model_reference       = var.image_builder_ollama_model_reference
  ollama_model_manifest_digest = var.image_builder_ollama_model_manifest_digest
  build_image_now              = var.build_image_now
  tags                         = local.common_tags
}

module "gpu" {
  count  = var.enable_gpu ? 1 : 0
  source = "./modules/gpu"

  name                = local.name
  ami_id              = local.selected_gpu_ami_id
  instance_type       = var.gpu_instance_type
  root_volume_gib     = var.gpu_root_volume_gib
  max_runtime_minutes = var.gpu_max_runtime_minutes
  kms_key_arn         = module.data.kms_key_arn
  subnet_id           = module.network.private_subnet_ids[0]
  vpc_id              = module.network.vpc_id
  vpc_cidr            = var.vpc_cidr
  s3_prefix_list_id   = module.network.s3_prefix_list_id
  application_sg_id   = module.network.application_security_group_id
  model_port          = var.model_port
  tags                = local.common_tags
}

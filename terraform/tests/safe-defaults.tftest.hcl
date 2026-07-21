mock_provider "aws" {}

override_data {
  target = data.aws_caller_identity.current
  values = { account_id = "123456789012" }
}

override_data {
  target = module.network.data.aws_availability_zones.available
  values = { names = ["eu-west-2a", "eu-west-2b"] }
}

run "safe_cost_defaults" {
  command = plan

  variables {
    owner       = "test-owner"
    cost_center = "test-cost-centre"
  }

  assert {
    condition     = var.enable_gpu == false
    error_message = "The chargeable runtime GPU must remain disabled by default."
  }

  assert {
    condition     = var.enable_ssm_endpoints == false && length(module.network.ssm_endpoint_ids) == 0
    error_message = "Hourly-billed SSM interface endpoints must remain disabled by default."
  }

  assert {
    condition     = var.enable_image_builder == false && var.build_image_now == false
    error_message = "The chargeable GPU image builder and immediate build must remain opt-in."
  }

  assert {
    condition     = var.enable_model_artifact_bucket == false && output.model_artifact_bucket_name == null
    error_message = "Model storage must remain opt-in and absent from the safe default plan."
  }

  assert {
    condition     = output.approved_gpu_ami_id == null
    error_message = "Safe defaults must not select an unapproved runtime AMI."
  }
}

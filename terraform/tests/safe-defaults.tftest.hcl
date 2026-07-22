# This test plans the root module without creating AWS resources. Provider data is
# replaced with deterministic values so the safety assertions run offline in CI.
mock_provider "aws" {}

# IAM and ARN construction require an account ID even though this is only a plan.
override_data {
  # `target` points to the exact data source being replaced in the module graph.
  target = data.aws_caller_identity.current
  # `values` acts like the result AWS would return from GetCallerIdentity.
  values = { account_id = "123456789012" }
}

# Two representative London availability zones allow the network module to plan
# its subnets without querying the live AWS account.
override_data {
  target = module.network.data.aws_availability_zones.available
  # The module can index and create its planned subnets from these fake AZ names.
  values = { names = ["eu-west-2a", "eu-west-2b"] }
}

run "safe_cost_defaults" {
  # `plan` evaluates the dependency graph and proposed resources but never calls
  # apply, so this test cannot create or modify infrastructure.
  command = plan

  # Required ownership tags use obviously non-production values in this test.
  variables {
    # These satisfy required root inputs exactly as a terraform.tfvars file would.
    owner       = "test-owner"
    cost_center = "test-cost-centre"
  }

  assert {
    # A default plan must never launch hourly-billed GPU compute implicitly.
    # `condition` is ordinary Terraform expression syntax evaluated against the plan.
    condition = var.enable_gpu == false
    # Terraform prints this sentence only when the condition evaluates to false.
    error_message = "The chargeable runtime GPU must remain disabled by default."
  }

  assert {
    # Interface endpoints charge per AZ-hour, so personal sessions enable them
    # explicitly and remove them afterwards rather than paying continuously.
    # && requires both the input flag and the resulting module output to be safe;
    # length(...) catches a module that creates endpoints despite the false flag.
    condition     = var.enable_ssm_endpoints == false && length(module.network.ssm_endpoint_ids) == 0
    error_message = "Hourly-billed SSM interface endpoints must remain disabled by default."
  }

  assert {
    # Image Builder can start temporary GPU infrastructure; both creation and an
    # immediate build are therefore separate, explicit opt-in decisions.
    condition     = var.enable_image_builder == false && var.build_image_now == false
    error_message = "The chargeable GPU image builder and immediate build must remain opt-in."
  }

  assert {
    # Even low-cost storage should not appear until the model-staging workflow is
    # selected, keeping an untouched deployment free from model artefact charges.
    # Checking the output as well as the variable verifies the planned graph, not
    # merely that the root input happens to contain its documented default.
    condition     = var.enable_model_artifact_bucket == false && output.model_artifact_bucket_name == null
    error_message = "Model storage must remain opt-in and absent from the safe default plan."
  }

  assert {
    # No mutable or placeholder image may become the runtime AMI by default. A
    # reviewed Image Builder output or explicit approved AMI must supply this ID.
    condition     = output.approved_gpu_ami_id == null
    error_message = "Safe defaults must not select an unapproved runtime AMI."
  }
}

# AWS infrastructure

This Terraform scaffold creates private networking, an encrypted and versioned
S3 bucket, a customer-managed KMS key, least-privilege application policies and,
only when explicitly enabled, a private GPU inference host.

The default plan creates no GPU or hourly-billed Systems Manager interface
endpoints. The GPU subnet has no internet gateway or NAT route. Personal
administration enables one-AZ SSM endpoints only for the session. Model artefacts
should be baked into the AMI or supplied through the optional private model
artefact bucket.

## Use

1. Authenticate to the intended AWS account with a short-lived identity.
2. Copy `terraform.tfvars.example` to an untracked `terraform.tfvars` and edit it.
3. Run `terraform init`, `terraform plan -out tfplan`, review the plan, and then
   run `terraform apply tfplan`.
4. Attach the output application data policy to the application's execution role.

Before a shared deployment, configure a remote S3 state backend with locking.
Backend configuration is intentionally environment-specific and is not hard-coded
here. Terraform state can contain sensitive infrastructure metadata and must be
encrypted and access-controlled.

## Cost allocation tags

The AWS provider automatically applies the following protected tags to every
resource type that supports tagging, including resources created by child modules:

- `Project`
- `Environment`
- `ManagedBy`
- `Owner`
- `CostCenter`
- `Repository`

`owner` and `cost_center` are required Terraform inputs. The optional `tags` map
can add reporting dimensions such as `Workload`, but it cannot override the
protected keys. The optional GPU instance carries an `AutoStop` tag describing
its instance-side systemd watchdog. By default it shuts itself down two hours
after every boot, even if the controlling laptop or terminal has disappeared.
The watchdog explicitly resets its timer after each restart, so stopping and
later starting the same instance always begins a fresh allowance. Its root EBS
volume receives the standard tags explicitly.

After the first tagged resources are created, activate the user-defined tag keys
in AWS Billing and Cost Management under **Cost allocation tags**. Until they are
activated, AWS will store the resource tags but will not expose them as Cost
Explorer or cost-reporting dimensions. Tag activation is an AWS account-level
operation and is deliberately not performed by this workload Terraform stack.

## Enabling private inference

Create and patch a hardened AMI containing the driver and inference service, set
`enable_gpu = true`, and provide its AMI ID. The instance receives no public IP.
Only workloads carrying the application security group may reach the model port.
The control policy permits start/stop only for the tagged GPU instance.

For personal use, follow the [personal session
runbook](../ops/runbooks/personal-session.md). Set `enable_ssm_endpoints = true`
only around a shell or Ollama tunnel session and return it to `false` after the
GPU is stopped. The default uses `ssm` and `ssmmessages` in one availability
zone; production deployments can set `ssm_endpoint_subnet_count = 2`.

## Cost and lifecycle choices

`enable_gpu = true` means Terraform should retain an EC2 GPU instance. It does
not mean the instance must run continuously. The session helper starts it and
`scripts/stop-gpu.ps1` stops it; stopped instances have no GPU/CPU compute
charge, but their retained root EBS volume still has a storage charge.

SSM interface endpoints are separate hourly-billed network resources. To remove
them after a session, create and review a plan with the same variable file used
for the deployment, for example:

```powershell
terraform plan `
  -var-file "../.local/aws-build.tfvars" `
  -var "enable_ssm_endpoints=false" `
  -out ssm-off.tfplan
terraform apply ssm-off.tfplan
```

If your inputs are in `terraform.tfvars` instead, Terraform loads them
automatically and the `-var-file` line is unnecessary. `ssm-off.tfplan` is a
binary saved plan, not source code; inspect it with
`terraform show -no-color ssm-off.tfplan` before applying it.

Do not use `terraform destroy` merely to end a session. It is for retiring the
whole project and will intentionally stop on non-empty transcript, model and
build-log buckets. A complete retirement also requires a deliberate decision
about the Image Builder AMI and its snapshots; KMS key deletion has a 30-day
safety window.

Set `gpu_max_runtime_minutes` to the longest session you intend to permit. This
is a hard cost-safety backstop; the session helper normally stops the instance
earlier when its tunnel or shell closes.

## Building the inference AMI

To bake a model, first set `enable_model_artifact_bucket = true` and apply the
reviewed storage-only plan. Then follow the [model staging
runbook](../ops/runbooks/stage-model.md). The script downloads an immutable
Hugging Face revision, checks its SHA-256, verifies the bucket controls, and
uploads it with KMS encryption. It prints the exact Terraform inputs needed by
Image Builder. You may instead set `image_builder_model_s3_bucket` to an existing
reviewed private bucket.

Set `enable_image_builder = true` with a pinned AWS GPU DLAMI, exact Ollama
version, and release-published SHA-256 digest. Terraform creates a manually
triggered EC2 Image Builder pipeline but does not run it by default. Temporary
build/test instances use a separate VPC with no inbound security-group rules.
They have HTTPS egress to retrieve the exact release and contact AWS APIs; this
does not change the isolated runtime VPC.

The AWSTOE build component verifies NVIDIA, verifies the `.tar.zst` before
extraction, sets `OLLAMA_NO_CLOUD=1`, installs a hardened systemd service, and can
download one exact GGUF object from S3, verify it, and import it. The test-stage
component launches the baked image and verifies NVIDIA and Ollama. When a model
is staged, it also performs a real generation and requires Ollama to report GPU
use. A model-less build deliberately skips only the inference test.

Start the output pipeline ARN from approved CI or operations tooling. Setting
`build_image_now = true` instead starts chargeable GPU build/test instances during
`terraform apply`. Successful distribution writes the tested private AMI ID to
the output `aws:ec2:image` SSM parameter. On a later deployment, set
`gpu_ami_ssm_parameter_name` to that path so the runtime resolves only the AMI
published after successful tests. The parameter must exist before Terraform can
read it.

Image Builder component and recipe versions are immutable. Bump
`image_builder_component_version` whenever either AWSTOE template changes and
`image_builder_recipe_version` whenever recipe inputs change.

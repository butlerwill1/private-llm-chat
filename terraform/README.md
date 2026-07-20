# AWS infrastructure

This Terraform scaffold creates private networking, an encrypted and versioned
S3 bucket, a customer-managed KMS key, least-privilege application policies and,
only when explicitly enabled, a private GPU inference host.

The default plan creates no GPU and therefore incurs no GPU-instance charge.
The GPU subnet has no internet gateway or NAT route. Administration uses AWS
Systems Manager through VPC endpoints. Model artefacts should be baked into the
AMI or supplied through a separately reviewed private artefact path.

## Use

1. Authenticate to the intended AWS account with a short-lived identity.
2. Copy `terraform.tfvars.example` to an untracked `terraform.tfvars` and edit it.
3. Run `terraform init`, `terraform plan -out=tfplan`, review the plan, and then
   run `terraform apply tfplan`.
4. Attach the output application data policy to the application's execution role.

Before a shared deployment, configure a remote S3 state backend with locking.
Backend configuration is intentionally environment-specific and is not hard-coded
here. Terraform state can contain sensitive infrastructure metadata and must be
encrypted and access-controlled.

## Enabling private inference

Create and patch a hardened AMI containing the driver and inference service, set
`enable_gpu = true`, and provide its AMI ID. The instance receives no public IP.
Only workloads carrying the application security group may reach the model port.
The control policy permits start/stop only for the tagged GPU instance.


# Deploy infrastructure

## Preconditions

- Use a short-lived AWS identity for the intended account and `eu-west-2` region.
- Confirm an approved remote-state bucket and lock table exist for shared use.
- Keep secrets out of Terraform variables, state, tags and command history.
- Confirm the AWS budget and GPU service quota before enabling inference compute.

## Procedure

1. From `terraform/`, copy `terraform.tfvars.example` to `terraform.tfvars` and
   adjust non-secret settings.
2. Run `terraform fmt -check -recursive` and `terraform validate`.
3. Run `terraform plan -out=tfplan`. Review every create, update and delete,
   paying particular attention to IAM, routing, security groups, KMS and S3.
4. Apply the reviewed file with `terraform apply tfplan`.
5. Record the deployment reference and outputs in the approved operations system.
6. Verify S3 Block Public Access, KMS rotation, CloudTrail coverage and VPC routes.

Do not apply a plan after its source, variables or provider selections change.
Create and review a new plan instead. Production changes require peer approval.

## Rollback

Prefer a forward fix. If rollback is required, check whether schema or stored-data
changes make the earlier version unsafe. Never destroy the conversation bucket or
KMS key as an incidental rollback step. Their Terraform protections and delayed
key deletion are intentional.


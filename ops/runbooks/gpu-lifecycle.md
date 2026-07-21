# Operate the private GPU host

## Start and readiness

1. Start only the instance ARN returned by Terraform, using the dedicated GPU
   control role.
2. Wait for EC2 system and instance checks to pass.
3. Confirm the inference service is healthy from application compute over its
   private address. Do not test by opening the model port to the internet.
4. Send a non-sensitive synthetic prompt before accepting user traffic.

## Stop

Drain or reject new inference requests, allow active requests a bounded time to
finish, then stop the instance. Confirm its state becomes `stopped`. Configure an
application idle timer and a budget alarm so an abandoned instance is noticed.

## Administration and patching

Use Systems Manager Session Manager through the private endpoints. There is no
inbound SSH rule. Build a replacement, scanned AMI and roll forward rather than
installing packages interactively. The subnet has no general internet egress;
model weights and dependencies must use an approved private artefact path.

## Build and approve a replacement AMI

1. Select an AWS-owned GPU DLAMI compatible with the target GPU family and pin
   its AMI ID. Record its publisher and release evidence in the change review.
2. Pin an Ollama version and verify the release asset's published SHA-256.
3. If baking a model, follow the [model staging runbook](stage-model.md) to put a
   pinned, checksum-verified GGUF in approved S3 storage. Configure its exact
   bucket, key, digest, and Ollama name.
4. Bump the component version for template changes and the recipe version for
   recipe or input changes. Apply the pipeline definition without running it.
5. Start the pipeline ARN from approved tooling. GPU build and test instances are
   chargeable and run in the separate no-ingress build VPC.
6. Approve only a successful Image Builder test stage. With a model, this includes
   a real generation and an Ollama processor report showing GPU use.
7. Confirm successful distribution updated the output `aws:ec2:image` parameter.
   Set `gpu_ami_ssm_parameter_name` to that path, review the plan, and replace the
   stopped runtime host. Run the standard readiness checks before use.

Do not deploy an untested intermediate AMI or select one using a mutable name/tag
filter. Retain the previous approved AMI until replacement readiness checks pass.

If someone proposes a public IP, `0.0.0.0/0` model rule, SSH rule or NAT route,
stop and require a threat-model review. Those changes violate the intended design.

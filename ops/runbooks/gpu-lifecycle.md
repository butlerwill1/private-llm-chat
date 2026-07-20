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

If someone proposes a public IP, `0.0.0.0/0` model rule, SSH rule or NAT route,
stop and require a threat-model review. Those changes violate the intended design.


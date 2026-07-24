# Operations guide

This directory contains the runbooks for operating the personal AWS deployment.
They are intentionally separate from application code because they include
cost-sensitive and security-sensitive actions.

## Runbooks

- [Personal session](runbooks/personal-session.md): start a private GPU session,
  run the local app, use OpenRouter-only mode, and stop chargeable resources.
- [GPU lifecycle](runbooks/gpu-lifecycle.md): understand the instance, AMI
  replacement and hardening lifecycle.
- [Model staging](runbooks/stage-model.md): download, verify and place an
  immutable GGUF in the private model bucket.
- [Infrastructure deployment](runbooks/deploy-infrastructure.md): validate and
  apply the Terraform stack.
- [Security incident](runbooks/security-incident.md): preserve safe evidence and
  rotate affected credentials after a suspected incident.

## Operating rule

Treat a Terraform plan as a proposed change, not a command to apply blindly.
Review every planned create, change and destroy. In particular, stop the GPU and
remove SSM interface endpoints after a private session; both resources are
chargeable while running or provisioned respectively.

# ADR 0002: Keep GPU inference on a private network

- Status: accepted
- Date: 2026-07-20

## Context

Users require a web interface, but that does not require the model-serving process itself to be internet-reachable.

## Decision

Expose only the authenticated application entry point. Place optional GPU EC2 instances in private subnets without public IP addresses. Permit the model port only from the application security group. Use Systems Manager and private AWS service endpoints for administration where practical.

## Consequences

- The application tier mediates authentication, redaction, encryption and lifecycle operations.
- Model downloads must be staged through a controlled egress path, S3 endpoint or pre-built image.
- The GPU can be stopped without making the control plane or encrypted conversation store unavailable.


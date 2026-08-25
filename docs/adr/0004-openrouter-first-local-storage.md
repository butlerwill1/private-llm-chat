# ADR 0004: Use encrypted local storage and privacy-restricted OpenRouter by default

- Status: accepted
- Date: 2026-08-24

## Decision

The default personal runtime keeps conversation ciphertext in a local SQLite
database and protects the local AES-256-GCM envelope master key with Windows
DPAPI in current-user scope. Inference uses a reviewed, model-specific OpenRouter
provider route with ZDR, data-collection denial and disabled fallbacks.

AWS Terraform, S3/KMS and self-hosted GPU adapters remain optional. Normal local
startup must not contact AWS.

## Consequences

DPAPI protects copied local storage while the user is offline, but does not
protect against malware or a process running as that Windows user. There is no
recovery export: an unavailable Windows profile makes chats unrecoverable.

OpenRouter/provider receives request plaintext during inference. This is
privacy-restricted hosted inference, not end-to-end private inference. The
adapter rejects provider drift instead of widening routing for availability.

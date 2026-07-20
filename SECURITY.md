# Security policy

This is a personal learning project, not a public multi-user service. Treat any deployment as security-sensitive because it processes private conversation content.

## Reporting a problem

Do not open a public issue containing credentials, prompts, conversation text, infrastructure identifiers or exploit details. Revoke exposed credentials first, preserve only non-sensitive diagnostic evidence, and use a private reporting channel agreed by the repository owner.

## Non-negotiable controls

- The browser never receives model-provider or AWS credentials.
- The GPU host has no public IP and exposes no public SSH or model-serving port.
- Stored conversation payloads use application-level authenticated encryption in addition to AWS storage encryption.
- Plaintext prompts and responses are excluded from logs, traces, metrics, crash reports and exception messages.
- OpenRouter routing is allowlisted and must fail closed when privacy restrictions cannot be satisfied.
- Dependencies, container images and model artefacts are pinned and reviewed before use with sensitive data.

See [the threat model](threat-model.md) for trust boundaries and residual risks.

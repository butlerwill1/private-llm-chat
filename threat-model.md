# Threat model

This is a living threat model for the private LLM chat service. Review it when
data flows, identity providers, model providers or deployment boundaries change.

## Assets and trust boundaries

The highest-value assets are message plaintext, encryption keys, authentication
tokens, user memory, model prompts and responses, and infrastructure credentials.
Ciphertext in S3 crosses the application-to-AWS boundary. A request to OpenRouter
crosses an external-provider boundary. A request to the private GPU crosses the
application-to-inference boundary but remains inside the VPC.

The browser and public API are untrusted entry points. The application runtime,
AWS account, CI system, administrators, OpenRouter and private inference host are
distinct trust zones. Compromise of one must not automatically grant every other
zone's privileges.

## Principal threats and controls

| Threat | Consequence | Primary controls | Residual risk / next action |
| --- | --- | --- | --- |
| Unauthorised account access | Plaintext conversation disclosure | Strong identity provider, MFA, short sessions, server-side authorisation on every object | Add rate limits and anomalous-login alerts |
| Public model endpoint exposure | Prompt theft or arbitrary GPU use | No public GPU IP, isolated subnet, security-group identity allow-list | Continuously audit network configuration |
| Storage disclosure | Conversation or memory exposure | Application envelope encryption, KMS, S3 Block Public Access, TLS-only bucket policy | State and backups also need access reviews |
| Key misuse | Bulk decryption | Separate KMS/data policy, least-privilege runtime role, CloudTrail | Add alerting for unusual decrypt volume |
| Prompt leakage through logs | Sensitive plaintext retained outside intended storage | Structured redaction, no request bodies in logs, regression tests | Third-party libraries require review |
| OpenRouter policy drift | Data reaches an unapproved provider or retention mode | Fail-closed adapter with ZDR/provider rules, contract tests | Provider claims and terms require periodic review |
| Prompt injection | Model follows hostile content and discloses context or invokes tools | Treat content as untrusted, minimise context, tool allow-lists, explicit confirmation | Models cannot provide a complete security boundary |
| Summary or memory drift | Incorrect details persist and influence later answers | Preserve source transcript, provenance links, regenerate from sources, correction/deletion UI | Inferred memories must remain visibly labelled |
| Compromised inference image | Model data or credentials exfiltrated | Vetted pre-baked AMI, no general egress, IMDSv2, minimal instance role, patch process | Establish signed-image promotion and vulnerability scanning |
| Excessive control-plane permissions | Attacker starts/stops or replaces unrelated compute | Dedicated control role scoped to exact tagged instance | Prevent policy changes through deployment-role separation |
| Dependency or CI compromise | Malicious code reaches production | Lock files, review gates, read-only CI defaults, scanning | Pin actions to commit SHAs for higher assurance |
| Resource exhaustion | High cost or unavailable service | GPU disabled by default, quotas, budgets, idle shutdown, rate limits | Define maximum session and queue limits |

## Privacy and deletion

The original encrypted transcript is authoritative. Summaries and memories are
derived records and must carry source message identifiers, creation time and
status (`inferred`, `confirmed`, `corrected` or `deleted`). User deletion must
cover current objects, versions, derived records, cached context and wrapped data
keys according to the documented retention policy. Backups must have a stated
expiry rather than an indefinite exception.

## Security assumptions

- AWS account administrators are trusted but auditable.
- Application plaintext exists briefly in process memory to serve a request.
- TLS terminates only at an approved managed endpoint or application service.
- A private subnet reduces reachability; it does not make vulnerable software safe.
- The optional external model path is less private than local inference and must be
  an explicit, visible user choice.


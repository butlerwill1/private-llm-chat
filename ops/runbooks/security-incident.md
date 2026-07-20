# Respond to a suspected privacy or security incident

## Immediate actions

1. Preserve timestamps, alerts and request identifiers without copying message
   plaintext into tickets or chat.
2. Disable the affected application or control role and revoke active sessions.
3. Isolate affected compute with a quarantine security group. Do not delete the
   instance or logs before evidence requirements are understood.
4. If external-model leakage is suspected, disable that backend at configuration
   level and retain its provider/request identifiers.
5. Notify the service owner and follow the organisation's incident process.

## Investigation

Review CloudTrail, identity-provider events, application security events, KMS key
usage, S3 data events, network-flow evidence and deployment history. Keep an audit
trail of queries and exports. Restrict evidence access and encrypt exports.

## Recovery

Rotate compromised credentials and keys where the evidence supports it, rebuild
compute from a trusted image, close the initial access path, and test controls
before restoring traffic. KMS rotation alone does not re-encrypt existing data;
plan explicit re-encryption if key material or decrypt authority was exposed.

Complete a post-incident review with affected data, time window, root cause,
control failures, user/legal notification decisions and assigned corrective work.


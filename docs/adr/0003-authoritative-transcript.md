# ADR 0003: Treat transcripts as authoritative and summaries as derived

- Status: accepted
- Date: 2026-07-20

## Context

Generated summaries are lossy and can omit or invent details. Repeatedly summarising an earlier summary amplifies drift.

## Decision

Keep the encrypted source transcript as the authoritative record. Store summaries and memories as separately encrypted, versioned derivatives with provenance. Distinguish inferred from user-confirmed memories and allow correction or deletion. Regenerate derived context from source messages after material corrections.

## Consequences

- Context can remain compact without pretending generated summaries are exact.
- The UI needs memory review and correction controls in a later phase.
- Deletion workflows must account for transcript objects, derived objects, versions and wrapped data-encryption keys.


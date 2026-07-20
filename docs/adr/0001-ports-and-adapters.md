# ADR 0001: Ports and adapters for external services

- Status: accepted
- Date: 2026-07-20

## Context

The application must support OpenRouter and a self-hosted model without coupling conversation, encryption or API logic to either backend. AWS services also need local substitutes for fast unit tests.

## Decision

Application services depend on typed Python `Protocol` ports. Concrete provider, persistence, encryption and lifecycle implementations live in adapters and are selected in a composition root.

Pydantic is used for transport and configuration validation. It is not used as a substitute for business services or provider interfaces.

## Consequences

- Model and storage implementations can be tested with shared contract suites.
- Business rules can be tested without network access.
- Additional files and explicit dependency wiring are required, but dependency direction remains visible.


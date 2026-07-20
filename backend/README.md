# Private AWS Chatbot backend

This directory contains a Python 3.12 FastAPI starter organised around clean/hexagonal
architecture. HTTP, inference vendors, persistence and key management are adapters around
application-owned interfaces. The `SendMessage` use case contains the business workflow and
can be tested without a network or framework.

## Security posture

- Message content is encrypted before it reaches the repository. The included in-memory
  repository and local key wrapper are development/test adapters, not production persistence.
- Each message gets a random AES-256-GCM data key. Authenticated context binds ciphertext to
  its conversation and message identifiers.
- OpenRouter calls always request zero-data-retention, deny data collection, disable provider
  fallbacks and use a non-empty provider allow-list. Responses without a confirmed allowed
  provider are rejected.
- The self-hosted adapter accepts only explicit loopback or private IP addresses. This avoids
  accidentally pointing the "private" route at a public host.
- Application code does not log prompts, responses, secrets or request bodies. Infrastructure
  access logs must follow the same rule.
- Configuration fails at startup when the encryption key or selected provider credentials are
  absent. There is no plaintext fallback.

Authentication, durable encrypted persistence and an AWS KMS `DataKeyProvider` are deliberately
deployment work, not implied by these local adapters. Do not expose this starter to a network
until authentication and authorisation are added at the API edge.

## Run locally

Create and activate a virtual environment, then from this directory:

```powershell
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Replace `CHAT_LOCAL_MASTER_KEY_B64` with the output of:

```powershell
python -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Start an OpenAI-compatible Ollama or vLLM endpoint, then run:

```powershell
uvicorn private_chat.main:app --reload
```

The API documentation is at `http://127.0.0.1:8000/docs` in development only.

## Quality checks

```powershell
ruff check .
mypy src
pytest
```

The contract tests are shared expectations for all inference adapters. New model integrations
should implement `ModelClient` and pass the same contract rather than changing the use case.

## Production adapter checklist

1. Implement `DataKeyProvider` with AWS KMS `GenerateDataKey` and `Decrypt`, including an
   encryption context.
2. Replace the in-memory repository with a durable adapter that stores ciphertext and supports
   atomic turn writes.
3. Put authentication and per-user conversation authorisation in front of every conversation
   route.
4. Inject secrets from an AWS secrets service; do not place them in images or Terraform state.
5. Disable or redact request-body logging in API Gateway, load balancers, tracing and error tools.

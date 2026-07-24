# Private AWS Chatbot backend

This directory contains a Python 3.12 FastAPI starter organised around clean/hexagonal
architecture. HTTP, inference vendors, persistence and key management are adapters around
application-owned interfaces. The `SendMessage` use case contains the business workflow and
can be tested without a network or framework.

## Security posture

- Message content is encrypted before it reaches either repository. The in-memory
  repository and local key wrapper are development adapters; personal mode can
  instead use conditional S3 writes and AWS KMS data keys.
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

The backend includes opt-in S3 persistence and an AWS KMS `DataKeyProvider` for
personal mode. Authentication remains deployment work: bind this process only to
`127.0.0.1` and do not expose it to a network until authentication and
authorisation are added at the API edge.

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

For durable personal storage, set `CHAT_STORAGE_BACKEND=s3` together with the
Terraform conversation bucket, KMS key and region outputs. The active local AWS
identity must carry the output application data policy. Each message remains
application-encrypted before S3 receives it; bucket SSE-KMS is an additional
storage control.

## Model modes and API behaviour

- **Self-hosted mode** is the default. The backend calls an OpenAI-compatible
  Ollama or vLLM endpoint, normally the local end of the SSM tunnel at
  `http://127.0.0.1:11434/v1`.
- **OpenRouter-only mode** is started with
  `..\\scripts\\start-openrouter-backend.ps1`. It requires an API key and a
  reviewed provider allowlist in the current shell. The helper does not start
  AWS resources or a GPU.
- `GET /v1/models` returns the backend-approved model catalogue. The browser
  cannot use a model ID outside that catalogue unless custom OpenRouter models
  were explicitly enabled.
- `GET /v1/conversation-summaries` returns only sidebar metadata. It avoids
  decrypting every conversation when the interface first opens.

Self-hosted requests have a finite, configurable timeout
(`CHAT_MODEL_RESPONSE_TIMEOUT_SECONDS`, default 300 seconds). A tunnel or model
timeout is returned as HTTP 504 rather than leaving the browser request open
indefinitely. The browser displays completed responses only; token streaming is
not yet part of the API contract.

## Quality checks

```powershell
ruff check .
mypy src
pytest
```

The contract tests are shared expectations for all inference adapters. New model integrations
should implement `ModelClient` and pass the same contract rather than changing the use case.

## Production adapter checklist

1. Put authentication and per-user conversation authorisation in front of every conversation
   route.
2. Integration-test S3 conditional writes and KMS encryption contexts in the deployment account.
3. Inject secrets from an AWS secrets service; do not place them in images or Terraform state.
4. Disable or redact request-body logging in API Gateway, load balancers, tracing and error tools.

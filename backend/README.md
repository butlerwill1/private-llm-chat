# Private AWS Chatbot backend

This directory contains a Python 3.12 FastAPI starter organised around clean/hexagonal
architecture. HTTP, inference vendors, persistence and key management are adapters around
application-owned interfaces. The `SendMessage` use case contains the business workflow and
can be tested without a network or framework.

## Security posture

- Message content and conversation titles are encrypted before they reach any
  repository. Default personal mode uses local SQLite and a Windows
  DPAPI-protected master key; S3/KMS remains an optional AWS adapter.
- Each message and title gets a random AES-256-GCM data key. Authenticated context
  binds a ciphertext to its conversation and specific field, so it cannot be
  substituted for a different record.
- Existing SQLite and S3 documents with plaintext legacy titles are migrated to
  encrypted titles when the app first reads them. Conversation IDs, creation times,
  active model IDs and message ordering remain storage metadata.
- OpenRouter calls always request zero-data-retention, deny data collection, disable provider
  fallbacks and use a non-empty provider allow-list. Responses without a confirmed allowed
  provider are rejected.
- The self-hosted adapter accepts only explicit loopback or private IP addresses. This avoids
  accidentally pointing the "private" route at a public host.
- Application code does not log prompts, responses, secrets or request bodies. Infrastructure
  access logs must follow the same rule.
- Configuration fails at startup when the encryption key or selected provider credentials are
  absent. There is no plaintext fallback.

The backend includes an encrypted local SQLite repository by default, plus opt-in
S3 persistence and an AWS KMS `DataKeyProvider` for a future AWS deployment.
Authentication remains deployment work: bind this process only to
`127.0.0.1` and do not expose it to a network until authentication and
authorisation are added at the API edge.

## Run locally

Create and activate a virtual environment, then from this directory:

```powershell
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Set `CHAT_OPENROUTER_API_KEY` in the ignored `.env` file, then run:

```powershell
..\scripts\start-local-chat.ps1
```

The API documentation is at `http://127.0.0.1:8000/docs` in development only.

The default Windows key is protected by DPAPI for the current Windows account.
There is deliberately no recovery export: reinstalling Windows or losing that
account makes existing local chats unrecoverable. The `.env` API key is plaintext
and ignored by Git; treat it as a spend-capable credential and rotate it if exposed.

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
- `PATCH /v1/conversations/{id}/model` changes the persistent conversation model
  and writes an encrypted timeline event. `POST /v1/conversations` can select an
  approved initial model. The message endpoint always uses the conversation's
  saved model rather than accepting a provider choice from the browser.
- `CHAT_INSTRUCTIONS_FILE` may point to an ignored local Markdown/text file.
  Its contents are injected into inference as local system instructions, never
  stored in the transcript or returned from an API.
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

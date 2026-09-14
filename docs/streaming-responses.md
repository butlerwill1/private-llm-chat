# Streaming responses and stable reading

Local Ollama and OpenRouter replies now appear incrementally. The browser paints received text at most once per animation frame: no artificial typing delay, and no wait for the complete answer. Providers may deliver several tokens per chunk.

## Reading controls

- At the start of a reply, its beginning is positioned near the top of the reading area once. More text then grows below it without automatically scrolling.
- **Follow latest** is off by default. Enable it to follow the end of the response. Scrolling or touching the reading area disables following.
- **Jump to latest** moves to the end once without enabling following.
- **Stop** cancels the browser request and closes the backend's provider stream. A partially received answer remains on screen as a draft; discard it before sending another message. Leaving the conversation or locking/reloading the app discards that in-memory draft.
- Streamed answers remain plain text, including Markdown punctuation, even when generation finishes. **Format answer** deliberately renders Markdown when you choose, avoiding an automatic layout change while reading. Previously saved answers are rendered as Markdown when reloaded.
- Reasoning models can show **Thinking…** before answer text arrives. Separate reasoning content is not displayed or stored.

## Implementation

The existing non-streaming endpoint remains available. The web app uses `POST /v1/conversations/{id}/messages/stream`, with the same request body as the ordinary messages endpoint.

The backend reads the provider's server-sent events incrementally and forwards newline-delimited JSON:

| Event | Meaning |
| --- | --- |
| `status` | Waiting or thinking; contains `text` |
| `text` | An answer fragment; contains `text` |
| `heartbeat` | Keeps an otherwise idle connection active |
| `done` | Contains the final saved `conversation` |
| `error` | Contains a sanitized explanation; not a successful completion |

UTF-8 characters and protocol frames may cross network chunks; both decoders retain incomplete data. The backend uses a bounded queue for backpressure. Disconnects cancel the producer and close the upstream HTTP response. A per-conversation guard rejects overlapping sends within the single backend process. A multi-worker deployment would require a shared concurrency guard.

Only a successful provider completion is passed to the existing encrypted transcript write. Incomplete streams are not intentionally saved or reused as context. If cancellation or a network failure races with the final database commit, reload the conversation to confirm whether that completed turn was saved. Requests are not automatically retried, avoiding duplicate generations and charges.

OpenRouter's provider allowlist, no-fallback, denied data-collection and zero-data-retention settings are preserved. Returned provider identity is checked before answer text is forwarded. Performance telemetry remains operational metadata only; it does not receive answer chunks, prompts, reasoning text, or upstream error bodies.

The browser uses a stable-height reading area and controls. Automatic scroll anchoring and changing offscreen-height estimates are disabled in the transcript. Fixed spacer space allows short answers to complete without the browser clamping the scroll position. Completion does not switch the answer to Markdown automatically.

## Verification

From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
.\backend\.venv\Scripts\python.exe -m ruff check backend
.\backend\.venv\Scripts\python.exe -m mypy backend/src
cd frontend
pnpm exec vitest run --maxWorkers=1
pnpm lint
pnpm build
```

Tests cover incremental delivery, split Unicode, stream errors, provider restrictions, final usage, cancellation without saving an incomplete turn, and manual reading controls. Browser layout checks should additionally verify that the first visible answer line and composer keep their vertical positions through both streaming and completion, at desktop and mobile sizes.

If deployed behind a reverse proxy, disable response buffering for the streaming endpoint and allow long-lived responses. The endpoint sends `Cache-Control: no-store` and `X-Accel-Buffering: no`; proxy configuration must honour streaming as well.

Cancellation of remote generation and billing depends on the underlying provider; closing our connection is not a universal guarantee that a cloud model immediately stops. See [OpenRouter streaming and cancellation](https://openrouter.ai/docs/api_reference/streaming). Local streaming uses [Ollama's OpenAI-compatible API](https://docs.ollama.com/api/openai-compatibility).

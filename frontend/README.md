# Private Chat frontend

This directory contains the browser interface for Private Chat. It is a React 19, Vite and strict TypeScript application with a deliberately small integration boundary: UI components depend on the `ChatApi` interface, not on HTTP or a particular model provider.

## Run locally

Use Node.js 20 or newer.

```powershell
pnpm install
pnpm run dev
```

Vite prints the local address when it starts. The application uses `HttpChatApi`
and proxies `/v1` to FastAPI on `127.0.0.1:8000`. Tests retain `DemoChatApi` as a
fast interface-compatible test double.

## Quality checks

```powershell
pnpm run lint
pnpm run test
pnpm run build
```

## Architecture

- `src/domain/chat.ts` owns the stable application types and the `ChatApi` interface.
- `src/data/httpChatApi.ts` is the runtime HTTP adapter; `demoChatApi.ts` is its in-memory test double.
- `src/components/` contains focused UI components with typed inputs and semantic markup.
- `src/App.tsx` composes the screen and owns only screen-level state.

`src/data/httpChatApi.ts` owns response validation, error mapping and transport
details. UI components continue to work only with the domain-level `ChatApi`.

## Current interface behaviour

- Assistant messages render safe Markdown, including headings, lists, links and
  code blocks. Raw HTML is not enabled.
- The settings dialog selects from the model catalogue returned by the backend.
  In OpenRouter-only mode it can optionally allow an explicitly enabled custom
  model ID.
- Responses are displayed after generation completes. While a request is in
  progress, the composer is disabled and a status message explains that the
  local model is generating.
- Conversation navigation initially loads metadata only; opening a conversation
  fetches and decrypts that conversation on demand.

The settings dialog does not claim to show GPU telemetry. GPU temperature,
utilisation and VRAM use require a separate authenticated telemetry endpoint and
are deliberately left out of the browser for now.

## Accessibility and privacy

The interface uses labelled controls, landmark elements, visible keyboard focus, live message announcements and a responsive navigation disclosure. The encryption label describes the application contract; frontend copy must not be treated as proof that encryption is correctly configured. Infrastructure and backend tests must verify that promise independently.

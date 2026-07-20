# Private Chat frontend

This directory contains the browser interface for Private Chat. It is a React 19, Vite and strict TypeScript application with a deliberately small integration boundary: UI components depend on the `ChatApi` interface, not on HTTP or a particular model provider.

## Run locally

Use Node.js 20 or newer.

```powershell
pnpm install
pnpm run dev
```

Vite prints the local address when it starts. The default development experience uses `DemoChatApi`, so the main workflows can be explored without cloud credentials or a running backend.

## Quality checks

```powershell
pnpm run lint
pnpm run test
pnpm run build
```

## Architecture

- `src/domain/chat.ts` owns the stable application types and the `ChatApi` interface.
- `src/data/demoChatApi.ts` is an in-memory adapter used for local development and tests.
- `src/components/` contains focused UI components with typed inputs and semantic markup.
- `src/App.tsx` composes the screen and owns only screen-level state.

When the backend API is available, add an HTTP implementation of `ChatApi` and inject it in `main.tsx`. Keep authentication, validation, error mapping and transport concerns inside that adapter; components should continue to work with domain types only.

## Accessibility and privacy

The interface uses labelled controls, landmark elements, visible keyboard focus, live message announcements and a responsive navigation disclosure. The encryption label describes the application contract; frontend copy must not be treated as proof that encryption is correctly configured. Infrastructure and backend tests must verify that promise independently.

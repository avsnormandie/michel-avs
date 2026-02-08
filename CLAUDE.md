# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**OpenClaw** (this fork: **Michel** for AVS Technologies) is a personal AI assistant platform written in TypeScript/Node.js. It connects to messaging channels (WhatsApp, Telegram, Slack, Discord, Google Chat, Signal, iMessage, Microsoft Teams, Matrix, etc.) through a central Gateway control plane, routes messages to AI agents (Pi agent runtime), and supports native apps (macOS, iOS, Android).

This is a fork of the upstream [OpenClaw/Clawdbot](https://github.com/openclaw/openclaw) project, customized for AVS Technologies' internal use. See `MICHEL.md` for AVS-specific customizations and `AGENTS.md` for the assistant persona configuration.

## Build & Development Commands

```bash
pnpm install                    # Install dependencies (pnpm 10.23+, Node >=22.12.0)
pnpm build                      # Full build: bundle UI + tsdown transpile + copy assets
pnpm dev                        # Dev mode with auto-reload (runs TS directly via tsx)
pnpm gateway:watch              # Dev loop for gateway (auto-rebuild on changes)

pnpm check                      # Run all checks: type-check + lint + format
pnpm tsgo                       # TypeScript type-check only (native TS compiler)
pnpm lint                       # OxLint with type-aware rules
pnpm format                     # Check formatting with OxFmt
pnpm format:fix                 # Auto-fix formatting
pnpm lint:fix                   # Auto-fix lint + format issues

pnpm test                       # Run unit/integration tests (parallelized via scripts/test-parallel.mjs)
pnpm test:watch                 # Watch mode
pnpm test:coverage              # With V8 coverage (70% threshold for lines/functions/statements)
pnpm test:e2e                   # E2E tests (vitest.e2e.config.ts)
pnpm test:live                  # Live API tests (requires OPENCLAW_LIVE_TEST=1 + API keys)

pnpm ui:build                   # Build the Control UI (Lit + Vite)
pnpm ui:dev                     # Dev server for Control UI
pnpm protocol:check             # Verify protocol schema + Swift codegen are in sync
```

Run a single test file:
```bash
npx vitest run src/path/to/file.test.ts
```

Before submitting a PR: `pnpm build && pnpm check && pnpm test`

## Architecture

```
Channels (WhatsApp/Telegram/Slack/Discord/...)
         │
         ▼
┌─────────────────────────┐
│   Gateway (WebSocket)   │  ← control plane: sessions, channels, tools, events, cron
│   ws://127.0.0.1:18789  │     HTTP API (Hono) + Control UI + WebChat
└────────────┬────────────┘
             │
      ┌──────┼──────────┬──────────┐
      ▼      ▼          ▼          ▼
   Pi Agent  CLI     macOS app   iOS/Android nodes
   (RPC)   (openclaw)
```

### Key source directories (`src/`)

- **`gateway/`** — WebSocket server, HTTP API, session management, config, protocol handling
- **`agents/`** — Agent orchestration, Pi agent RPC bridge, tool definitions, model selection/failover
- **`channels/`** — Unified channel abstraction layer (dock pattern for message routing)
- **`cli/` + `commands/`** — CLI entry point and command implementations (`openclaw <command>`)
- **`telegram/`, `discord/`, `slack/`, `signal/`, `imessage/`** — Channel-specific integrations
- **`sessions/`** — Session model (main, group isolation, activation modes, queue modes)
- **`media/` + `media-understanding/`** — Media pipeline (images, audio, video, transcription)
- **`infra/`** — Infrastructure utilities (Tailscale, networking, platform detection)
- **`config/`** — Configuration loading and validation
- **`plugins/` + `plugin-sdk/`** — Plugin/extension system and SDK
- **`tts/`** — Text-to-speech (ElevenLabs, Edge TTS)
- **`browser/`** — Browser control (Playwright/CDP)
- **`cron/`** — Scheduled tasks and wakeups

### Other important directories

- **`ui/`** — Control UI web app (Lit web components + Vite build)
- **`extensions/`** — Pluggable channel/auth extensions (33 extensions)
- **`skills/`** — Skill plugins (56+ skills including avs-brain for persistent memory)
- **`apps/`** — Native apps: `ios/` (Swift), `android/` (Gradle), `macos/` (Swift)
- **`packages/`** — pnpm workspace packages: `clawdbot/`, `moltbot/`
- **`scripts/`** — Build, test, and utility scripts

### Entry points

- `openclaw.mjs` — CLI entry (bin target)
- `src/index.ts` / `src/entry.ts` — Main module entry points
- `src/extensionAPI.ts` — Extension/plugin API surface

## Key Conventions

### TypeScript
- **Strict mode** enabled, target ES2023, module NodeNext
- **Legacy decorators** (`experimentalDecorators: true`, `useDefineForClassFields: false`) — required by the Lit-based Control UI. Do not switch to standard decorators without updating UI build tooling.
- Calendar-based versioning: `YYYY.M.D`

### Testing
- **Vitest** with `pool: "forks"` for test isolation
- Test files: `*.test.ts` (unit), `*.e2e.test.ts` (e2e), `*.live.test.ts` (live API, excluded from normal runs)
- Multiple vitest configs: `vitest.config.ts` (main), `vitest.e2e.config.ts`, `vitest.live.config.ts`, `vitest.unit.config.ts`, `vitest.gateway.config.ts`, `vitest.extensions.config.ts`
- Test timeout: 120s; coverage provider: V8

### Linting & Formatting
- **OxLint** (Rust-based) with type-aware rules, plugins: unicorn, typescript, oxc
- **OxFmt** for formatting
- **SwiftLint + SwiftFormat** for iOS/macOS code
- Git hooks via `git-hooks/` directory (set by `pnpm prepare`)

### Security
- Treat inbound DMs as untrusted input
- DM pairing by default (allowlist-based access)
- Never hardcode API keys — use environment variables (`$AVS_API_KEY`)
- Use `trash` over `rm` for recoverable deletion

## Upstream Sync

```bash
git remote add upstream https://github.com/clawdbot/clawdbot.git
git fetch upstream
git merge upstream/main --no-edit
```

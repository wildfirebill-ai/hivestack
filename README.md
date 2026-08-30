# hivestack — Local-First AI Agent Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker Image](https://img.shields.io/badge/Docker-ghcr.io%2Fwildfirebill--ai%2Fhivestack-blue)](https://ghcr.io/wildfirebill-ai/hivestack)
[![Unraid Template](https://img.shields.io/badge/Unraid-Community%20Apps-green)](docker/unraid-template.xml)
[![Security Scan](https://github.com/wildfirebill-ai/hivestack/actions/workflows/security-scan.yml/badge.svg)](https://github.com/wildfirebill-ai/hivestack/actions/workflows/security-scan.yml)
[![CI](https://github.com/wildfirebill-ai/hivestack/actions/workflows/ci.yml/badge.svg)](https://github.com/wildfirebill-ai/hivestack/actions/workflows/ci.yml)

**hivestack** is a **local-first AI agent and AIOps platform** that runs **fully offline** on a Tesla M40 (Maxwell, CC 5.2). It ships as a single Docker/Unraid app with a Web UI. Every cloud provider (OpenAI, Anthropic, Gemini, etc.) sits behind its own **enable switch** — local-only by default.

> **Status**: Stage 12 — Distro & Hardening (in progress). Stages 0–11 complete. Offline e2e suite: 14/14 ✅

---

## Why hivestack?

| Problem | hivestack Solution |
|---------|-------------------|
| **Cloud dependency** | Runs 100% offline — no API keys required for core features |
| **Data privacy** | Your data never leaves your hardware (M40 GPU or CPU) |
| **Provider lock-in** | Unified provider gate: switch between local Ollama and cloud models instantly |
| **Complex setup** | Single container deploy via Docker Compose or Unraid Community Apps |
| **Observability gap** | Built-in AIOps: telemetry, alerts, RCA, chaos testing, postmortems |

---

## Core Features

### 🔒 Provider Gate — Zero Cloud by Default
- **Global `offline_mode`** — hard block on all cloud calls (returns `403 PROVIDER_DISABLED`)
- **Per-provider toggles** — OpenAI, Anthropic, Gemini, Ollama each independently enabled
- **Credentials only read** when both `offline_mode=false` AND provider enabled
- **Zero network calls** in default configuration

### 💬 Chat & Agents
- **Streaming chat** via SSE with provider auto-selection
- **Agent runtime** — plan→act loop with scoped tools, step caps, cancel flags
- **Tool sandbox** — calculator, filesystem, shell, web fetch (offline-gated), MCP client/server
- **MCP support** — acts as both MCP server and MCP client

### 🧠 Memory & Knowledge (RAG)
- **Hybrid search** — local embeddings (`all-MiniLM-L6-v2` via fastembed/ONNX) + FTS5 keyword
- **Temporal knowledge graph** — entities/relations with validity windows
- **Compaction** — summaries archive originals, token-budget context packing

### 🔄 Workflows & Orchestration
- **Persisted DAGs** — tool/agent/chat/wait/map/board steps with parallel waves
- **Checkpoints + resume** — approval stops, retries, `{step}`/`{item}` substitution
- **Cron scheduler** — interval/cron triggers with daemon

### 📋 Kanban Boards
- Boards → columns → cards with drag-drop moves
- Workflow `board` steps emit cards automatically

### 🛠 Skills & Packaging
- Versioned skill registry injected into agent runs
- Generator with template/LLM-author modes, eval trial runs
- Portable SKILL.md export, install from local paths or git (offline-gated)

### 📄 Studio: Documents, Data & Media
- **Word** — sections, tables, `{{field}}` merge with preview/audit/diff
- **Excel** — sheets + live formulas, CSV/JSON profiling, anomaly detection
- **PowerPoint** — builders with approval-gated local outbox publishing

### 📡 Comms & Voice
- Channels: webhook, email, Telegram, Discord, Slack, Matrix (external = offline-gated)
- Reply pipeline: agent → RAG-chat → memory-backed offline fallback
- Encrypted secrets vault (Fernet), wake-word → STT → agent → TTS loop

### 🚨 AIOps (Full Observability Loop)
- **Telemetry ingestion** — points + logs with windowed queries
- **Anomaly detection** — z-score, IQR, Isolation Forest
- **Alerts** with ack/close, **service topology + RCA** engine
- **Incidents** with timelines, **remediation** with approval → recovery verification
- **Chaos fault-injection** — demo targets: fault → detect → alert → incident → RCA → approve & verify
- **One-call demo**: `POST /api/aiops/demo` drives full loop

### 🛡 Governance & Security
- **RBAC** — admin/operator/viewer with PBKDF2
- **Immutable audit log** — wired into toggles, approvals, vault, self-service
- **Token budgets** — daily + per-run cost caps enforced in agent runtime
- **Security posture** self-review dashboard

### 💰 Economy (Experimental, Opt-In)
- Local escrow/gig marketplace with ledger
- ECDSA signature identity + one-time nonce challenges (anti-replay)
- Signed federation pings via `/api/federation/ingest`

---

## Quick Start

### Docker Compose (Linux/macOS/Windows)

```bash
git clone https://github.com/wildfirebill-ai/hivestack.git
cd hivestack
cp .env.example .env
# Edit .env: set HIVESTACK_ADMIN_PASSWORD=your-strong-password
docker compose -f docker/docker-compose.yml up -d
# Open http://localhost:8080 → login: admin / your-password
```

### Unraid Community Apps

1. Install **NVIDIA GPU Plugin** + **Driver 580 branch** (required for M40/CC 5.2)
2. **Apps → Search "hivestack" → Install**
3. Set paths: `/config`, `/data`, `/models` (defaults work)
4. Set **Admin password** (required)
5. Optional: **GPU UUID(s)** = `all` for M40
6. Apply → Web UI at `http://<unraid-ip>:8080`

### Local Development

```bash
# Linux/macOS
python3 -m venv .venv && ./.venv/bin/pip install -r backend/requirements.txt
./scripts/dev.sh          # API :8110 + Web :5173

# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
.\scripts\dev.ps1
```

---

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **GPU** | Tesla M40 (24 GB VRAM, CC 5.2) | Same |
| **Driver** | NVIDIA 580 branch (Linux) | Same |
| **System RAM** | 16 GB | 32 GB |
| **Disk** | 20 GB free | 50 GB free (models + data) |
| **CPU** | 4 cores | 8+ cores |

> **Note**: Stage 1 (core platform) runs CPU-only. Stage 2+ (local inference via Ollama) requires M40 GPU.

---

## Documentation

| Guide | Description |
|-------|-------------|
| [Getting Started](docs/getting-started.md) | Docker Compose & Unraid quick start |
| [Configuration](docs/configuration.md) | All config.yaml options, env overrides, security |
| [Provider Management](docs/providers.md) | Enable/disable cloud & local providers |
| [Unraid Guide](docs/unraid.md) | Template install, GPU setup, backup/restore |
| [API Reference](docs/api.md) | REST endpoints, auth, WebSockets, errors |
| [Architecture](docs/architecture.md) | System design, data flow, invariants |

---

## Testing & Quality

```bash
make test          # pytest unit suite
make e2e           # offline end-to-end suite (14 scenarios, must exit 0)
make typecheck     # TypeScript strict mode
make build         # Docker image
```

**CI Pipeline** runs on every push/PR:
- Offline e2e suite (no network calls)
- Security scan: gitleaks + pip-audit + npm audit + Trivy image scan
- Results aggregated to `vulnerabilities.md`

---

## Release & Backup

```bash
# Version lives in VERSION file (source of truth)
./scripts/build.sh                    # build locally
./scripts/release.sh                  # build + push to GHCR
git tag -a v$(cat VERSION) -m "Release v$(cat VERSION)" && git push origin v$(cat VERSION)

# Backup / restore
python scripts/backup.py --data /data --config /config --out ./backups
python scripts/backup.py --restore ./backups/hivestack-backup-<ts>.zip --dest ./restore
```

---

## Architecture Decisions

| ADR | Title | Status |
|-----|-------|--------|
| [0001](docs/adr/0001-sqlite-wal-migrations.md) | SQLite WAL + Migrations | Accepted |

---

## Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for:
- Branching strategy, commit conventions
- Local test commands (`make test && make e2e && make typecheck`)
- Architecture invariants (offline-first, provider gate, DB migrations)
- Security reporting: **security@wildfirebill.ai**

---

## Security

- **Never commit secrets** — `.env`, `.env.*`, `runtime/` are gitignored
- **Report vulnerabilities privately**: security@wildfirebill.ai
- Automated scanning: gitleaks, pip-audit, npm audit, Trivy (weekly + on push)
- See [SECURITY.md](.github/SECURITY.md) for full policy

---

## License

**MIT License** — see [LICENSE](LICENSE) for details.

Copyright (c) 2024 wildfirebill-ai

---

## Links

- **Web UI**: `http://<host>:8080`
- **API Docs (Swagger)**: `http://<host>:8080/docs`
- **Health Check**: `http://<host>:8080/health/ready`
- **GitHub**: https://github.com/wildfirebill-ai/hivestack
- **Issues**: https://github.com/wildfirebill-ai/hivestack/issues
- **Discussions**: https://github.com/wildfirebill-ai/hivestack/discussions
- **Security**: security@wildfirebill.ai
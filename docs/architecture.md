# hivestack — Architecture

Local-first AI agent / AIOps platform. Runs fully offline on a Tesla M40 (Maxwell,
CC 5.2), ships as a single Docker/Unraid app, and is driven through a Web UI. Every
outside provider sits behind an **off switch** — local-only by default.

## Shape

A **modular monolith**: FastAPI app + static React/Vite UI in one image, SQLite for
persistence, feature modules registered on a bus, and a single **provider gate** for all
model/API traffic.

```
Web UI (React/Vite) ─► FastAPI routers ─► feature modules
                                              │
                    Provider gate (offline lockout + per-provider switches)
                                              │
                              Local: Ollama/CPU · Cloud (opt-in)
                                              │
                              SQLite (WAL) + embeddings ─ /data
```

## Core modules

- **Provider gate** — `offline_mode` + per-provider `enabled`. Cloud refused (403) offline.
- **Chat / inference** — local Ollama + cloud adapters (SSE); CPU fallback (`provider: fallback`).
- **Agents** — bounded plan→act loop, scoped tools, sandbox, MCP server + client.
- **Workflows / boards** — DAG engine, scheduler, kanban.
- **Memory / RAG** — hybrid search (CPU embeddings + FTS5), temporal knowledge graph.
- **Skills / Studio** — skills registry + generator; docs/data/media builders.
- **Comms / Voice** — channels, stealth vault, STT/TTS loop.
- **AIOps** — telemetry, anomaly detection, RCA, remediation, chaos demo.
- **Governance / Economy** — RBAC, budgets, audit; opt-in economy.

## Storage

- Single SQLite file at `/data/hivestack.db`, **WAL** journal, foreign keys, busy timeout.
- Schema versioned via `PRAGMA user_version` + `MIGRATIONS` (`app/db.py`).
- `/config` (config.yaml), `/data` (SQLite + telemetry/chunks), `/models` (weights) volumes.

## Ops surface

- `/health` liveness; `/health/ready` deep readiness (DB + modules); `/metrics` Prometheus;
  `/api/system/usage` token+cost export.
- `docker/maintenance.sh` — periodic VACUUM + dated backups.
- `scripts/backup.py` — backup / verify / restore.
- CI: `ci.yml` (offline e2e), `release.yml` (GHCR), `security-scan.yml` (`vulnerabilities.md`).

## Key decisions

Recorded in `docs/adr/` and `../PLAN.md` §5. Notable: modular monolith (D1), Ollama (D2),
custom agent runtime (D5), built-in workflow engine (D7), hybrid memory (D8), CPU
embeddings (D9), single-file SQLite (D15).

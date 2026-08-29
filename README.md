# hivestack

Local-first AI agent / AIOps platform. Runs fully offline on a Tesla M40 (Maxwell, CC 5.2),
ships as a single Unraid Docker app, and drives everything through a Web UI. Every outside
provider sits behind its own **off switch** — local-only by default.

> Status: **Stage 11 — Economy, Identity & Federation done (experimental)**. Next: **Stage 12 — Distro & Hardening**.

## What works today

- **Provider gate** — global `offline_mode` lockout + per-provider enables; cloud providers refused (403) while offline.
- **Real chat** — chat routes to a registered model through normalized adapters: local **Ollama** and cloud **OpenAI / Anthropic / Gemini** (SSE streaming). CPU fallback available (`provider: fallback`).
- **Model registry + prompt studio + usage accounting** — register/enable/default/test models, async Ollama pull, named system prompts, per-provider token accounting.
- **Agent runtime** — bounded plan→act loop over the gate; a run is created from a goal, the agent calls **scoped tools** per turn, and every step lands as an audited `run_event`. Cancel flag, step cap, clean error surfacing.
- **Tool registry + sandbox** — `calculator`, `list_workspace`, `read_file`, `write_file` (workspace-confined), `shell` (env-isolated, timed, `/dev/null` stdin), `web_fetch` (blocked in offline mode). Per-run `allowed_scopes` gate each call.
- **MCP** — hivestack acts as an MCP **server** (`python -m app.mcp_server_entry`) and as an MCP **client** (`mcp_servers` config, stdio + streamable HTTP) whose tools join the agent registry behind the network gate.
- **Workflows & scheduling** — persisted DAG workflows (`tool`/`agent`/`chat`/`wait`/`map`/`board` steps) with parallel waves, retries, checkpoints + resume, and **approval stops** (pause → approve/deny → resume). Cron/interval **scheduler** daemon fires them. `{step}`/`{item}` substitution throughout.
- **Kanban boards** — boards/columns/cards with move; workflow `board` steps emit cards.
- **Memory & knowledge (RAG)** — verbatim memory store + chunks, hybrid search (local CPU embeddings `all-MiniLM-L6-v2` via fastembed/ONNX + FTS5 keyword), RAG ingest (text/csv/url/file with word-aware chunking), token-budget context packer, compaction-into-summaries (archives originals), and a temporal knowledge graph (entities/relations with validity + invalidation). Chat takes a `rag` flag; agents get a `memory_search` tool and an optional memory-injected run.
- **Skills & packaging** — versioned skill registry (instruction bundles injected into agent runs), a generator (template offline / LLM-author with fallback), structural validation + eval trial runs, portable SKILL.md export, and an install manager from local paths or git (offline-gated) with install-source sync-state.
- **Studio: documents, data & media** — Word (sections/tables/`{{field}}` merge), Excel (sheets + live formulas), and PowerPoint builders with preview/audit/diff; CSV/JSON profiling + log normalization + anomaly detection (z-score, IQR, Isolation Forest); image-gen/OCR wired behind graceful 501 when optional backends are absent; **approval-gated publishing** to a local outbox.
- **Comms & voice** — channels registry (webhook/email/telegram/discord/slack/matrix, external ones offline-gated), a reply pipeline that degrades agent → RAG-chat → **memory-backed offline fallback**, email/webhook ingest with optional workflow triggers, a mailbox audit log, an **encrypted secrets vault** (Fernet), and a wake-word → STT → agent → TTS loop (text path fully verifiable offline; real audio needs optional backends).
- **AIOps** — telemetry ingestion (points + logs) with windowed queries and anomaly detection (zscore/IQR/Isolation Forest); alerts with ack/close; a service **topology + RCA** engine (affected-set traversal + root scoring w/ memory hints); incidents with event timelines; **remediation with approval → recovery verification**; postmortems to the outbox; and **chaos fault-injection demo targets** whose threads write baseline→fault→recovery telemetry. One `/api/aiops/demo` call drives the full loop: fault → detect → alert → incident+RCA → approve & verify.
- **Governance** — RBAC users (admin/operator/viewer, PBKDF2), an **immutable audit log** wired into toggles/approvals/vault/self-service, **daily + per-run token budgets with cost caps** (enforced in the agent runtime — proven `budget_capped`), a verification gate for finished runs, an observability **dashboard** (tokens/cost/runs/incidents/alerts), and a security-posture self-review.
- **Economy (experimental, opt-in)** — local escrow/gig marketplace with a ledger, ECDSA signature identity with one-time nonce challenges (anti-replay), and signed federation pings via a public signature-authenticated `/api/federation/ingest`. Disabled by default; core unaffected.
- **Web UI** — dashboard, streaming chat, **Agents**, **Workflows**, **Boards**, **Memory**, **Skills**, **Studio**, **Comms**, **AIOps**, **Governance**, **Economy**, settings.
- **Docker / Unraid** — image (embedding model pre-cached offline), compose (GPU + `hivestack-ollama` sidecar), Unraid CA template, healthcheck.

## Layout

```
backend/          FastAPI app (config, provider gate, auth, chat, system, ws)
web/              React + Vite UI (built into the image at bake time)
docker/           Dockerfile, docker-compose.yml, entrypoint, Unraid template
scripts/          dev + build + GPU-check launchers
runtime/          local dev data/config/models (git-ignored; Docker uses /config /data /models)
```

## Quick start (dev)

```powershell
# Windows
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
.\scripts\dev.ps1            # API :8110  +  Web :5173  (login admin / hivestack)
```

```bash
# Linux/macOS
python3 -m venv .venv && ./.venv/bin/pip install -r backend/requirements.txt
./scripts/dev.sh
```

`npm install`/`build` happen automatically via the Docker build; only run them manually inside `web/`
if you're hacking on the UI.

## Offline end-to-end test

`tests/e2e_offline.py` drives the whole platform against a fresh uvicorn in a temporary runtime dir —
no network, no model required — and asserts every exit criterion from Stages 1-11:

```powershell
python tests/e2e_offline.py          # uses a random free port
python tests/e2e_offline.py 8110     # or pin a port
```

Exit code is non-zero if any scenario fails. It checks health/auth, the provider gate (cloud refused
offline), chat `provider: fallback` (returning `source: "fallback"`), memory hybrid search, skills
generate+validate, doc/word audit, comms+vault, workflow approval gates, agent run lifecycle,
AIOps fault→approve→verify, governance budget/RBAC, economy escrow, and studio publishing.

> On Windows the suite reconfigures stdout to UTF-8 so scenario names containing `→` / `·` never
> crash under the default cp1252 console. If a chat-fallback run reports a missing `"source"` key,
> a stale server/bytecode is serving an older build — kill any leftover uvicorn bound to the port
> (and clear `backend/app/routers/__pycache__`) before re-running.

## Docker / Unraid

```bash
./scripts/build.sh                             # build hivestack:0.1.0
docker compose -f docker/docker-compose.yml up # with optional: --profile gpu (adds Ollama)
```

On Unraid: install the NVIDIA driver plugin, keep the **580 branch** for Maxwell, then import
`docker/unraid-template.xml` into Community Apps (template registry values are placeholders until
first publish). Mount `/config`, `/data`, `/models` and set `HIVESTACK_ADMIN_PASSWORD`.

GPU sanity check: `./scripts/check-m40.sh` (should list the M40, CC 5.2).

## Roadmap

| Stage | Focus | State |
|------|-------|-------|
| 0 | Planning & decisions | ✅ |
| 1 | Foundation: API, provider gate, Web UI, Docker/Unraid shell | ✅ |
| 2 | Inference & model layer | ✅ |
| 3 | Agent core & tool runtime (scoped tools, sandbox, MCP) | ✅ |
| 4 | Orchestration, workflows & boards | ✅ |
| 5 | Memory & knowledge (RAG) | ✅ |
| 6 | Skills & packaging | ✅ |
| 7 | Documents, data & media | ✅ |
| 8 | Communications & voice | ✅ |
| 9 | AIOps module | ✅ |
| 10 | Governance, security & observability | ✅ |
| 11 | Economy, identity & federation (experimental) | ✅ |
| 12 | Distro & hardening | next |

## Chatting with a real model

1. Settings → Providers: ensure `ollama` enabled (local engines ignore offline mode).
2. Settings → Models: **pull** a weight (`qwen2.5:7b` fits an M40 easily), then **enable** a
   registry entry (or add your own name / model_id).
3. Chat page auto-selects the default model and streams through it.

On Unraid the app reaches the Ollama sidecar via `HIVESTACK_OLLAMA_URL=http://hivestack-ollama:11434`; locally it uses `http://127.0.0.1:11434` (set `HIVESTACK_OLLAMA_URL` to override).
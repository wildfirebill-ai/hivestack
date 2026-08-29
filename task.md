# task.md — hivestack work checklist

Notation: `[x]` done · `[ ]` todo · `[-]` blocked · `[~]` in progress
Owner: agent + human at each Stage gate. Master plan: `../PLAN.md`.

## Stage 1 — Foundation & Docker/Unraid shell

### Repo scaffold
- [x] Monorepo layout: `backend/`, `web/`, `docker/`, `scripts/`, `runtime/`
- [x] `.gitignore`, `.env.example`, `README.md`, `task.md`

### Backend (FastAPI gateway + provider gate)
- [x] Config loader (`config.yaml`, volume-aware paths, env overrides)
- [x] SQLite init (`data/hivestack.db`, kv + messages tables)
- [x] Auth: login → bearer token, `require_token` dependency
- [x] Provider gate: global `offline_mode` + per-provider enables, cloud locked when offline
- [x] System API: info, offline toggle, providers, modules, GPU
- [x] Chat API routed through gate; CPU-fallback responder
- [x] `/health` probe + `/ws` stub
- [x] Static Web UI serving (baked `dist`)
- [x] Smoke test: health/login/chat/gate-403/modules all pass (port 8110; 8000 reserved on this box)

### Web UI (React + Vite)
- [x] Login page
- [x] Layout (sidebar nav, logout)
- [x] Dashboard (system + GPU + modules cards)
- [x] Chat (fallback replies, source badge)
- [x] Settings (offline switch, provider toggles, module toggles)
- [x] `tsc --noEmit` clean, `vite build` green, static served by API

### Docker / Unraid
- [x] Multi-stage `Dockerfile` (node build → python runtime, HEALTHCHECK, volumes)
- [x] `entrypoint.sh` (seed config, GPU banner)
- [x] `docker-compose.yml` (NVIDIA gpu reservation + optional Ollama sidecar profile)
- [x] Unraid CA template (`docker/unraid-template.xml`)
- [–] Docker build on a real box with NVIDIA runtime (needs host/docker — not verifiable here)

## Stage 2 (next) — Inference & Model Layer ✅
- [x] Ollama engine adapter (native /api/chat JSON + NDJSON streaming, manage/unreachable handling)
- [x] Cloud adapters behind the gate — OpenAI, Anthropic, Gemini (SSE streaming + usage normalization)
- [x] Model registry (list/add/enable/delete/default/test) + Ollama pull (async, status-polled)
- [x] Prompt studio (named system prompts, CRUD)
- [x] Token/cost accounting (messages table columns + /api/system/usage aggregates)
- [x] Streaming end-to-end: `/api/chat` (non-stream) + `/api/chat/stream` (SSE), Chat UI consumes SSE
- [x] Web UI: model dropdown, streaming chat, Models & Prompts settings, usage card
- [x] Verified: 502 clean on unreachable local · 403 gate cloud-while-offline · fallback 200 · SSE events · usage rows
- [~] M40 GGUF pass on real hardware (pull e.g. qwen2.5:7b via Settings → Models → pull)

## Stage 3 — Agent Core & Tool Runtime ✅
- [x] Agent runtime: bounded plan→act loop over the provider gate (JSON tool-call protocol, verify → final answer)
- [x] Run lifecycle + audit: tasks + run_events; events started/llm/tool_call/tool_result/tool_denied/tool_error/completed/error/cancelled; cancel flag
- [x] Tool registry w/ scopes: calculator(low), list_workspace(low), read/write_file(medium, workspace-confined), shell(high), web_fetch(high+network — blocked offline)
- [x] Sandbox: workspace confinement (escapes blocked), env-isolated timed shell (stdin=/dev/null), safe AST calculator
- [x] Per-run policy (allowed_scopes; auto=ask → high denied w/ note); network tools denied in offline mode
- [x] MCP client manager (stdio + streamable HTTP) on a dedicated event loop; external tools = scope high + network
- [x] hivestack MCP server (system_info, gpu_info, tool_list, chat, run_agent) — `python -m app.mcp_server_entry`
- [x] Routers: agents tasks/tools + mcp; UI: Agents page (goal/name/model/steps/scopes, runs, tools, event detail), MCP panel in Settings
- [x] Verified: tool exec + denials · run→error lifecycle w/ events · list/detail · static UI · 6 tools
- [~] Real tool-calling round-trip + cancel-during-LLM on hardware (needs Ollama/M40)

## Stage 4 — Orchestration, Workflows & Boards ✅
- [x] Workflow engine: persisted DAG deps, wave-parallel execution (ThreadPool), per-step retries/backoff, failure-stop (continue_on_error opt-in)
- [x] Step types: tool, agent (runs an agent task), chat (completion), wait, map (parallel fan-out w/ {item}), board (emit kanban card); {step} + {item} substitution in args/goals/prompts
- [x] Checkpoints: every step result persisted to workflow_step_runs; resume re-runs only failed/pending; cancel flag
- [x] Approval stops: mode=approval pauses run (awaiting_approval) until approve/deny via API, then resumes
- [x] Scheduler daemon: cron (croniter) + interval schedules, next_run_at tracking, fires workflow runs (verified fire)
- [x] Kanban boards: boards/columns/cards CRUD + move; workflow `board` step emits cards; UI Boards page
- [x] UI: Workflows page (create via JSON, runs, step log, approve/deny/resume/cancel, schedules), Boards page
- [x] Verified: parallel+deps+board+approval gating+resume→completed · scheduler fired runs · CRUD round-trips · typecheck/build clean
- [~] LLM-heavy step (agent/chat) + map fan-out on hardware (needs Ollama/M40)

## Stage 5 — Memory & Knowledge (RAG) ✅
- [x] Verbatim memory store (notes) + chunks; originals never deleted (archive hides)
- [x] Hybrid search: CPU embeddings (fastembed/all-MiniLM on ONNX, cached, offline) + FTS5/LIKE keyword, fused; scope filter; snippet+score
- [x] RAG ingest: text / csv / url (gated offline) / file upload; word-aware chunking; retrieve w/ citations; context packer (token budget)
- [x] Context engine: char→token estimator, budget-fit packer (dropped count), used by chat RAG + agent memory hook
- [x] Compaction-with-archive: cluster similar notes (cos ≥ .88) → summary note, originals archived
- [x] Temporal KG: entities, links w/ validity + invalidation (valid_to), active-links query
- [x] memory_search tool registered for agents (offline-safe); chat `rag` flag injects memory context; agent runs can request `memory=true`
- [x] UI: Memory page (search, add note, ingest, compact, notes, KB); nav
- [x] Verified: hybrid retrieval, chunked ingest (9 chunks), URL gated offline, compaction merged→1 summary, KG invalidate, tool present
- [~] chat-rag + agent-memory injection require a live model to observe in replies (needs Ollama/M40)

## Stage 6 — Skills & Packaging ✅
- [x] Skill registry: versioned, named, taggable instruction bundles (skills table); CRUD + quarantine
- [x] Generator: deterministic template path (offline) + optional LLM authoring (falls back on no engine)
- [x] Validation: 5 structural checks → score + pass (verified score 1.0)
- [x] Eval: trial agent run with the skill injected → run id, status, steps, tokens
- [x] Agent integration: `skill` param injects instructions into the run's system prompt + `skill` event
- [x] Packaging/export: portable SKILL.md (frontmatter name/description/version+body) + manifest
- [x] Install manager: local path (SKILL.md or dir) and git (clone → parse → register); install sources with sync-state (present/missing; git head vs recorded sha)
- [x] git install gated by offline mode (403)
- [x] UI: Skills page (generate/create, install, validate/eval/export/delete, exported preview); nav
- [x] Verified: template generate → validate 1.0 → export frontmatter → local install → git 403 → source state present → eval() events started,skill,error when engine absent
- [~] LLM-authored skills + green eval pass need a live model (Ollama/M40)

## Stage 7 — Documents, Data & Media ✅ (engine-gated parts noted)
- [x] Doc engine: build Word (sections/bullets/tables + {{field}} mail-merge), Excel (sheets + live formulas preserved), PowerPoint (title/bullets) — preview/audit/diff + document registry
- [x] Data: CSV/JSON profiling (dtypes, numeric stats, categorical tops, insights); log normalization (JSON/key=value/access-log → structured records); anomaly detection hybrid (z-score + IQR) and Isolation Forest (sklearn) — verified both methods
- [x] Media: image generate (diffusers) + OCR (pytesseract) wired behind graceful 501 when backend deps absent — verified clean 501 offline
- [x] Publishing: approval-gated jobs (create → pending_approval → approve/deny → execute → outbox write); execute rejected until approved — verified
- [x] UI: Studio page (word/sheet builders, doc list w/ preview, data/analytics, publish queue); nav
- [x] Verified: word merge "Q3 2026" + table + audit pass · xlsx formulas · pptx · diff counts · analyze · anomalies hybrid+iso · publish flow · media 501 · typecheck/build clean
- [~] Real image generation + OCR need torch/diffusers + tesseract in the container (M40 fp32); LLM-driven doc authoring later

## Stage 8 — Communications & Voice ✅
- [x] Channels: config registry (webhook/email/telegram/discord/slack/matrix), each opt-in + offline-gated for external platforms
- [x] Reply pipeline: memory-injected agent run → RAG chat → offline memory-backed fallback (verified memory snippet appended offline)
- [x] Inbound dispatch: webhook + email ingest (subject/body), optional `trigger_workflow` start; mailbox audit log
- [x] Outbound send: webhook local-first; external connectors (telegram/discord/slack/matrix) refused 403 in offline mode
- [x] Encrypted vault: Fernet AES secret store, master key env or keyfile, values never listed
- [x] Voice: hotword (hivestack / hey|ok|hello hivestack) → STT (faster-whisper, optional) → reply → TTS (piper, optional); text-transcript path verifies the whole loop offline
- [x] UI: Comms page (channels, webhook tester, mailbox, vault, voice); nav
- [x] Verified: webhook+email ingest → memory-backed fallback reply · telegram 403 offline · vault set/get (values hidden on list) · voice activate (wake word + reply + memory) / no-wake false · TTS 501 · typecheck/build clean
- [~] Live token sends (Telegram/Discord/Slack/Matrix) + real STT/TTS audio need credentials + optional backends in the container

## Stage 9 — AIOps Module ✅
- [x] Telemetry ingestion (points + logs) + windowed query; anomaly detection reuse (zscore/IQR/isin) via /analyze
- [x] Alerts: create/ack/close + severity, persistence; detection→alert in demo flow
- [x] Topology + RCA: service graph (depends_on edges), affected-set traversal, root scoring (downstream × anomaly evidence, memory hints); /rca + triage
- [x] Incidents + events: opened/triaged/rca/remediation_requested/remediated/rollback/postmortem
- [x] Remediation w/ approval: approve → wait for chaos recovery → verify readings return to baseline → remediated + incident resolved; deny supported
- [x] Postmortem: template timeline → outbox file
- [x] Chaos: demo targets (web-api/db/worker) with baseline→fault→recovery telemetry threads; start/stop/state
- [x] One-shot demo: inject fault → auto-detect → alert → incident+RCA+suggestion (exit loop, fully offline)
- [x] UI: AIOps page (demo runner + approve/verify, incidents/events, alerts ack/close, chaos); nav
- [x] Verified FULL LOOP: demo(db,latency) ok=1 anomaly, root=db → approve verified=True → incident resolved (events opened,triaged,rca,remediation_requested,remediated) → postmortem file → alert/chaos/telemetry present
- [~] LLM-grounded RCA narrative + agent-driven triage need a model (Ollama/M40)

## Stage 10 — Governance, Security & Observability ✅
- [x] RBAC users (admin/operator/viewer) with PBKDF2 hashes; login by username; admin seeded from env; require_admin guard (ops blocked on admin routes — verified)
- [x] Immutable audit log (append-only) wired into offline/provider/module toggles, user mgmt, vault writes, publish approve/execute, AIOps remediation approve — verified entries
- [x] Budgets: daily token budget + per-run token limit + cost estimates; enforced in the agent runtime (allow_new_run + within_per_run). Verified: budget=0 → run status `budget_capped`
- [x] Verification gate: re-check a finished run (answer present, no tool errors, within budget) → verify endpoint
- [x] Dashboard: today tokens/calls/cost, runs/incidents/alerts status counts, audit/users, budget %
- [x] Security posture self-review (auth/gate/vault-encrypted/sandbox/audit-immutable/budgets/RBAC) → 100%
- [x] UI: Governance page (posture cards, budget bar + admin edit, users/RBAC, audit feed, security checks, verify gate); nav
- [x] Verified: RBAC 403 · audit trail · budget cap · dashboard · security review · typecheck/build clean
- [~] Real $ cost caps need provider pricing data per model (config fields exist)

## Stage 11 — Economy, Identity & Federation ✅ (experimental / opt-in)
- [x] Local economy simulation behind the `economy` module toggle (off by default; verified 403 gate off, enabled via Settings)
- [x] Accounts (user/agent, balances, reputation) + gig marketplace with escrow: open → claim → complete → settle (reward owner→performer, ledger entry, rep bump) — verified escrow +1/−1
- [x] Identity: ECDSA P-256 keypairs (private stored locally, dev-only), one-time nonce challenges, sign/verify — verified good/bad signatures + **anti-replay** (nonce consumed at verify; replay → "replay detected")
- [x] Federation: peers config + add endpoint, signed self-ping round trip via public `/api/federation/ingest` (signature-authenticated, no bearer token) — verified http 200 ok=True from=hivestack-node
- [x] UI: Economy page (accounts, gig escrow board, ledger, identity prove w/ replay check, peers + ping); nav
- [x] Verified: escrow/ledger · identity good+replay(false) · federation ping verified · typecheck/build clean
- [~] Multi-node federation, artifact/persona trading, GPG/key export, on-chain components — future

## Stage 12 (next) — Distro & Hardening

## Notes
- Local dev port is 8110 (8000 is reserved by Windows kernel on this machine).
- M40 CC 5.2 → Ollama/llama.cpp only; vLLM excluded (needs CC 7.5+). Driver branch 580 for Maxwell on Unraid.
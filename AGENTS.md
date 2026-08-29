# AGENTS.md

Guidance for AI coding agents and maintainers working in this repo.

## What this is

hivestack is a **local-first AI agent / AIOps platform** that runs fully offline on a
Tesla M40 (Maxwell, CC 5.2). It ships as a single Docker/Unraid app controlled through
a Web UI. Every outside provider sits behind a per-provider **off switch**; local-only
by default. Status: Stages 0–11 complete; Stage 12 (distro/hardening) in progress.

## Layout

```
backend/app/          FastAPI app (config, provider gate, auth, chat, agents, aiops, ...)
backend/app/routers/  HTTP routers, one per feature area
web/                  React + Vite UI (built into the image at bake time)
docker/               Dockerfile, compose, entrypoint, maintenance, Unraid template
scripts/              dev/build/test/backup/release helpers
tests/                offline e2e (tests/e2e_offline.py) + pytest unit (tests/unit/)
.github/              CI, release, security-scan workflows
```

## Key invariants (do not break)

- **Offline-first.** Core paths (chat, agents, memory, AIOps, docs) must work with zero
  cloud dependency. Cloud providers are gated by `offline_mode` + per-provider `enabled` —
  an explicitly-requested cloud provider while offline **must** return 403 (see
  `inference/client.py::_gate_required`).
- **Provider gate is the single choke point.** Route all model/API calls through it.
- **DB schema is versioned** via `PRAGMA user_version` + `MIGRATIONS` in `db.py`. Migrations
  are append-only; never edit an applied migration.
- **`/health` = liveness**, **`/health/ready` = deep readiness** (DB + modules). The Docker
  HEALTHCHECK relies on `/health/ready`.

## Commands

```bash
make dev          # run API locally
make test         # pytest unit suite (tests/unit)
make e2e          # offline end-to-end suite (must stay green: 14 scenarios)
make typecheck    # web/ TS type-check
make build        # Docker image
make backup       # dated backup of /data + /config
```

## Tests & security

- Run `make test` and `make e2e` before pushing. The e2e suite boots a fresh uvicorn in a
  temp dir and asserts 14 scenarios; it must pass with exit 0.
- The `Security scan` GitHub workflow scans the repo (gitleaks + pip-audit + npm audit) and
  the image (Trivy), writing `vulnerabilities.md`.
- Never commit secrets. `.env`, `.env.*`, `runtime/`, `.venv/` are gitignored; keep
  `.env.example` placeholders only.

## Conventions & environment quirks

- Decision log lives in `../PLAN.md` §5 — one implementation per feature; changing a pick is
  an explicit re-decision.
- Python deps in `backend/requirements.txt` (runtime) and `backend/requirements-dev.txt`
  (test-only). New runtime deps must be added to `requirements.txt` and installed into the
  image build.
- On Windows, stdout is cp1252 — the e2e suite and `backup.py` reconfigure stdout to UTF-8;
  keep that guard for any script that prints non-ASCII.
- Local dev port is 8110; M40 needs driver branch 580. vLLM is excluded (needs CC 7.5+).
- Structured JSON logging: use `from ..log import get_logger` in backend modules.

## Release

- `VERSION` is the source of truth for the image tag. `make release` builds + pushes
  `ghcr.io/wildfirebill-ai/hivestack:<VERSION>` and `:latest`.
- Cut an annotated `v${VERSION}` tag when releasing.

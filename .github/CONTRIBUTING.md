# Contributing to hivestack

Thank you for your interest in contributing! hivestack is a local-first AI agent platform
that runs fully offline on a Tesla M40 (Maxwell, CC 5.2). Every outside provider sits
behind a per-provider **off switch**; local-only by default.

## Quick Start

```bash
# 1. Clone & enter
git clone https://github.com/wildfirebill-ai/hivestack.git
cd hivestack

# 2. Create venv & install deps
make refresh

# 3. Run the API locally (port 8110)
make dev

# 4. Run tests
make test         # unit tests
make e2e          # offline end-to-end suite (14 scenarios)

# 5. Type-check the web UI
make typecheck
```

## Development Workflow

### Branching

* `main` — protected, always deployable
* Feature branches: `feature/<short-description>`
* Bug fixes: `fix/<short-description>`
* Docs: `docs/<short-description>`

### Commits

Follow [Conventional Commits](https://www.conventionalcommits.org/):
```
feat: add agent memory persistence
fix: handle empty config on first boot
docs: update AGENTS.md with new invariants
```

### Pull Requests

1. **Branch from `main`**, open PR against `main`
2. **Run the full test suite locally** before pushing:
   ```bash
   make test && make e2e && make typecheck
   ```
3. **CI must pass** (runs `make e2e` in a clean Ubuntu runner)
4. **Security scan runs automatically** on PR — check the `vulnerabilities.md` artifact
5. **Require at least one approval** from a CODEOWNER (see `CODEOWNERS`)

## Project Structure

```
backend/app/          FastAPI app (config, provider gate, auth, chat, agents, aiops, ...)
backend/app/routers/  HTTP routers, one per feature area
web/                  React + Vite UI (built into the image at bake time)
docker/               Dockerfile, compose, entrypoint, maintenance, Unraid template
scripts/              dev/build/test/backup/release helpers
tests/                offline e2e (tests/e2e_offline.py) + pytest unit (tests/unit/)
.github/              CI, release, security-scan workflows
```

## Key Invariants (Do Not Break)

1. **Offline-first.** Core paths (chat, agents, memory, AIOps, docs) must work with zero
   cloud dependency. Cloud providers are gated by `offline_mode` + per-provider `enabled` —
   an explicitly-requested cloud provider while offline **must** return 403 (see
   `inference/client.py::_gate_required`).

2. **Provider gate is the single choke point.** Route all model/API calls through it.

3. **DB schema is versioned** via `PRAGMA user_version` + `MIGRATIONS` in `db.py`. Migrations
   are append-only; never edit an applied migration.

4. **`/health` = liveness**, **`/health/ready` = deep readiness** (DB + modules). The Docker
   HEALTHCHECK relies on `/health/ready`.

## Adding Dependencies

* **Python runtime deps** → `backend/requirements.txt`
* **Python dev deps** → `backend/requirements-dev.txt`
* **JS deps** → `web/package.json`

After adding runtime deps, rebuild the Docker image:
```bash
make build
```

## Testing

| Command | Purpose |
|---------|---------|
| `make test` | pytest unit suite (tests/unit) |
| `make e2e` | offline end-to-end suite — **must pass with exit 0** (14 scenarios) |
| `make typecheck` | TS type-check the web app |

The e2e suite boots a fresh uvicorn in a temp dir and asserts 14 scenarios.
It runs fully offline — no network calls.

## Security

* Never commit secrets. `.env`, `.env.*`, `runtime/`, `.venv/` are gitignored.
* The `Security scan` workflow runs gitleaks + pip-audit + npm audit + Trivy on the image.
* Report vulnerabilities privately: **security@wildfirebill.ai** (see `SECURITY.md`)

## Release Process

1. Update `VERSION` file (source of truth for image tag)
2. Update `CHANGELOG.md`
3. Push a version tag: `git tag v0.1.0 && git push origin v0.1.0`
4. GitHub Actions `Release` workflow builds & pushes:
   - `ghcr.io/wildfirebill-ai/hivestack:<VERSION>`
   - `ghcr.io/wildfirebill-ai/hivestack:latest`

## Code Style

* **Python**: Black + Ruff (enforced in CI)
* **TypeScript**: ESLint + Prettier (enforced in CI, `make typecheck`)
* **Structured JSON logging**: use `from ..log import get_logger` in backend modules

## Questions?

Open a [Discussion](https://github.com/wildfirebill-ai/hivestack/discussions) or
check the [docs](https://github.com/wildfirebill-ai/hivestack/tree/main/docs).
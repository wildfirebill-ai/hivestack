# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1.0 | :x:                |

Only the latest minor release receives security patches. The project is pre-1.0;
breaking changes may occur between minor versions.

## Reporting a Vulnerability

**Do not open a public issue.** Report security vulnerabilities privately to:

**security@wildfirebill.ai**

Include:
- Description of the vulnerability
- Steps to reproduce (if possible)
- Affected components (e.g., provider gate, auth, DB migrations, GPU driver handling)
- Any known mitigations

We will:
1. Acknowledge within 48 hours
2. Provide a preliminary assessment within 5 business days
3. Coordinate a fix timeline (typically 7-30 days depending on severity)
4. Credit you in the advisory (unless you prefer anonymity)

## Security Architecture

hivestack is designed **local-first** with these security boundaries:

### Provider Gate (Single Choke Point)
All model/API calls route through `backend/app/inference/client.py::_gate_required`.
- Cloud providers require **explicit opt-in**: provider `enabled=true` + global `offline_mode=false`
- Offline mode = hard block: any cloud call returns **403** with error code `PROVIDER_DISABLED`
- No provider credentials are read unless both conditions are met

### Authentication
- Single admin user (configured via `HIVESTACK_ADMIN_USER` / `HIVESTACK_ADMIN_PASSWORD`)
- Session cookies: `HttpOnly`, `Secure` (in container), `SameSite=lax`
- Passwords: Argon2id via `passlib`
- No MFA in v0.1.x (planned for 0.2.0)

### Data Handling
- SQLite database at `/data/hivestack.db` (volume-mounted, user-controlled)
- No telemetry, no analytics, no phone-home
- Embedding model cached at build time (`/opt/hivestack-models/embed`) — zero network at runtime

### GPU / Driver Surface
- NVIDIA driver branch **580** required for M40 (CC 5.2)
- Container runs with `NVIDIA_VISIBLE_DEVICES` restriction (default `all`, configurable)
- No host GPU passthrough beyond CUDA compute

## Automated Security Scanning

| Tool | Scope | Frequency |
|------|-------|-----------|
| **gitleaks** | Repo secrets | Every push/PR + weekly |
| **pip-audit** | Python deps (`backend/requirements.txt`) | Every push/PR + weekly |
| **npm audit** | JS deps (`web/package.json`) | Every push/PR + weekly |
| **Trivy** | Docker image (OS + Python + Node layers) | Every push/PR + weekly |

Results aggregated into `vulnerabilities.md` and uploaded as workflow artifact.
On `main` branch, `vulnerabilities.md` is auto-committed.

## Known Limitations (v0.1.x)

- Single admin user (no RBAC)
- No audit logging of admin actions
- No rate limiting on auth endpoints
- WebSocket connections not authenticated separately
- Model cache (`/models`) writable by container user

## Disclosure Timeline

1. **Day 0**: Private report received
2. **Day 1-2**: Triage + reproduction
3. **Day 3-7**: Fix developed + tested (offline e2e suite)
4. **Day 7-14**: Patch release tagged (`v0.1.x+1`)
5. **Day 14**: Public advisory published (GitHub Security Advisory + `CHANGELOG.md`)

## Scope Exclusions

Out of scope for this policy:
- Vulnerabilities in upstream dependencies (report to those maintainers)
- Issues requiring physical access to the host machine
- Denial of service via resource exhaustion (GPU, RAM, disk) — user-controlled
- Social engineering / phishing targeting the admin user

## Contact

**security@wildfirebill.ai** — PGP key available on request.
# Pull Request Template

## Description

<!--
Briefly describe what this PR does. Link to any related issues.
Fixes #<issue_number>
-->

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Refactor / code cleanup
- [ ] CI/CD / workflow changes
- [ ] Security fix

## Checklist

### Testing
- [ ] `make test` passes (unit tests)
- [ ] `make e2e` passes (offline end-to-end suite — **14 scenarios, exit 0**)
- [ ] `make typecheck` passes (TypeScript strict mode)
- [ ] Manual testing done for affected features

### Code Quality
- [ ] No new `TODO`/`FIXME` comments without linked issue
- [ ] Structured JSON logging used (`from ..log import get_logger`)
- [ ] No hardcoded secrets, keys, or credentials
- [ ] Dependencies added to correct requirements file (`requirements.txt` vs `requirements-dev.txt`)

### Architecture Invariants
- [ ] **Offline-first preserved** — no new network calls in core paths
- [ ] **Provider gate respected** — all model calls route through `inference/client.py::_gate_required`
- [ ] **DB migrations append-only** — new migration added to `MIGRATIONS` in `db.py`, never edited existing
- [ ] **Health endpoints work** — `/health` (liveness) + `/health/ready` (deep readiness)

### Security
- [ ] No secrets in code, tests, or config examples
- [ ] Input validation on new endpoints
- [ ] Auth checks on new protected routes

### Documentation
- [ ] `CHANGELOG.md` updated (under `## Unreleased`)
- [ ] `AGENTS.md` updated if invariants/conventions changed
- [ ] README/docs updated if user-facing behavior changed

## Screenshots / Logs

<!--
If UI changes, add screenshots. If backend changes, add relevant log snippets.
-->

## Deployment Notes

<!--
Any special deployment considerations? Config changes? Migration steps?
- New environment variables?
- Volume mounts?
- GPU driver version?
-->

## Reviewer Notes

<!--
Anything specific you want reviewers to focus on?
-->
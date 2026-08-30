---
name: Security Issue
about: Report a security vulnerability (use email for sensitive details)
title: "[Security] "
labels: ["security"]
assignees: ""
---

## ⚠️ STOP — Do Not File Sensitive Details Here

**For actual vulnerabilities, email: security@wildfirebill.ai**

This template is for:
- Security hardening suggestions
- Dependency vulnerability discussions (after public disclosure)
- Architecture security reviews
- Threat model questions

## Category

- [ ] Dependency vulnerability (CVE in requirements.txt / package.json)
- [ ] Configuration hardening
- [ ] Authentication / authorization
- [ ] Input validation / injection
- [ ] Secrets management
- [ ] GPU / driver surface
- [ ] Other: _______

## Description

<!-- Non-sensitive description of the concern -->

## Affected Components

- [ ] Provider gate (`inference/client.py`)
- [ ] Authentication (`auth/`)
- [ ] Database (`db.py`, migrations)
- [ ] API endpoints (`routers/`)
- [ ] Web UI (`web/`)
- [ ] Docker / container (`docker/`)
- [ ] GPU handling (`entrypoint.sh`, `check-m40.sh`)
- [ ] Other: _______

## Suggested Mitigation

<!-- If you have a fix or workaround in mind -->

## References

<!-- Links to CVEs, advisories, related PRs -->

---

**Reminder**: Actual exploitable vulnerabilities → **security@wildfirebill.ai**
We acknowledge within 48h, assess in 5 business days, coordinate fix timeline.
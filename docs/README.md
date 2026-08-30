# Documentation Index

## User Guides

| Document | Audience | Description |
|----------|----------|-------------|
| [Getting Started](getting-started.md) | All users | Quick start for Docker Compose & Unraid |
| [Configuration](configuration.md) | Admins | All config.yaml options, env overrides, security |
| [Provider Management](providers.md) | Users | Enable/disable cloud providers, local Ollama |
| [Unraid Guide](unraid.md) | Unraid users | Template install, GPU setup, backup/restore |

## Reference

| Document | Audience | Description |
|----------|----------|-------------|
| [API Reference](api.md) | Developers | REST endpoints, auth, WebSockets, errors |
| [Architecture](architecture.md) | Contributors | System design, data flow, invariants |

## Architecture Decisions

| ADR | Title | Status |
|-----|-------|--------|
| [0001](adr/0001-sqlite-wal-migrations.md) | SQLite WAL + Migrations | Accepted |

## Quick Links

- **Web UI**: `http://<host>:8080`
- **API Docs (Swagger)**: `http://<host>:8080/docs`
- **Health Check**: `http://<host>:8080/health/ready`
- **GitHub**: https://github.com/wildfirebill-ai/hivestack
- **Issues**: https://github.com/wildfirebill-ai/hivestack/issues
- **Security**: security@wildfirebill.ai
# Configuration Reference

All configuration is in `/config/config.yaml` (seeded on first boot).
Environment variables override file values — see `.env.example`.

## Core Settings

```yaml
# Server
host: "0.0.0.0"           # bind address
port: 8080                # Web UI + API port

# Authentication
admin_user: "admin"       # username (from HIVESTACK_ADMIN_USER)
# admin_password: set via HIVESTACK_ADMIN_PASSWORD env var ONLY (not in YAML)

# Offline Mode (default: true)
offline_mode: true        # when true, ALL cloud providers return 403
                          # set false ONLY after enabling providers below
```

## Provider Gates (Per-Provider Opt-In)

Each provider has its own `enabled` switch. Credentials are **only read** when:
1. `offline_mode: false` AND
2. `provider.enabled: true`

```yaml
providers:
  openai:
    enabled: false
    # api_key: read from HIVESTACK_OPENAI_KEY env var
    model: "gpt-4o"
    timeout_seconds: 30

  anthropic:
    enabled: false
    # api_key: read from HIVESTACK_ANTHROPIC_KEY env var
    model: "claude-3-5-sonnet-20241022"
    timeout_seconds: 30

  gemini:
    enabled: false
    # api_key: read from HIVESTACK_GEMINI_KEY env var
    model: "gemini-1.5-pro"
    timeout_seconds: 30

  # Local Ollama (Stage 2) — no API key needed
  ollama:
    enabled: false
    base_url: "http://hivestack-ollama:11434"  # docker-compose service name
    model: "llama3.1:8b"
    timeout_seconds: 120
```

## Paths (Volume Mounts)

```yaml
paths:
  config_dir: "/config"      # this file lives here
  data_dir: "/data"          # SQLite DB, logs, backups
  models_dir: "/models"      # Ollama model cache (Stage 2)
  embed_cache: "/opt/hivestack-models/embed"  # baked into image
```

## Database

```yaml
database:
  path: "/data/hivestack.db"
  wal_mode: true             # WAL for concurrent reads
  backup_keep: 7             # daily backups to retain
  maint_interval_seconds: 86400  # 24h
```

## Logging

```yaml
logging:
  level: "INFO"              # DEBUG, INFO, WARNING, ERROR
  format: "json"             # structured JSON logs
  access_log: true           # HTTP access logs
```

## Feature Flags

```yaml
features:
  chat: true
  agents: true
  workflows: true
  boards: true
  memory: true
  skills: true
  studio: true
  comms: true
  aiops: true
  governance: true
  economy: true
  settings: true
```

## Environment Variable Overrides

All YAML keys can be overridden via `HIVESTACK_<SECTION>_<KEY>`:

| Env Var | YAML Path |
|---------|-----------|
| `HIVESTACK_PORT` | `port` |
| `HIVESTACK_OFFLINE_MODE` | `offline_mode` |
| `HIVESTACK_ADMIN_USER` | `admin_user` |
| `HIVESTACK_ADMIN_PASSWORD` | (secret, not in YAML) |
| `HIVESTACK_PROVIDERS_OPENAI_ENABLED` | `providers.openai.enabled` |
| `HIVESTACK_PROVIDERS_OPENAI_MODEL` | `providers.openai.model` |
| `HIVESTACK_PATHS_DATA_DIR` | `paths.data_dir` |

## Example: Enable OpenAI (Production)

```bash
# 1. Set env vars (in .env or container env)
HIVESTACK_OFFLINE_MODE=false
HIVESTACK_PROVIDERS_OPENAI_ENABLED=true
HIVESTACK_OPENAI_KEY=sk-...

# 2. Restart
docker compose restart hivestack
```

## Security Notes

- **Never commit `config.yaml` with real credentials** — use env vars
- `HIVESTACK_ADMIN_PASSWORD` **must** be set via env (not YAML)
- Provider API keys **only read** when both offline_mode=false AND provider enabled
- Rotate keys by updating env var + restart (no config file edit needed)
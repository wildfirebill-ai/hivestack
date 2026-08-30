# Provider Management

hivestack uses a **provider gate** — every cloud provider has its own enable switch.
**Local-first by default**: `offline_mode=true` blocks ALL cloud calls (returns 403).

## Architecture

```
User Request
    ↓
Provider Gate (inference/client.py::_gate_required)
    ↓
┌─────────────────────────────────────────────────┐
│ offline_mode=true? → 403 PROVIDER_DISABLED      │
└─────────────────────────────────────────────────┘
    ↓ (offline_mode=false)
┌─────────────────────────────────────────────────┐
│ provider.enabled=true? → 403 PROVIDER_DISABLED  │
└─────────────────────────────────────────────────┘
    ↓
Credentials read from ENV (only now)
    ↓
Provider API call
```

## Enabling a Cloud Provider

### 1. Set Credentials (Environment Variables)

```bash
# .env file (gitignored) or container env
HIVESTACK_OPENAI_KEY=sk-...
HIVESTACK_ANTHROPIC_KEY=sk-ant-...
HIVESTACK_GEMINI_KEY=AIza...
```

### 2. Disable Offline Mode + Enable Provider

**Option A: Config file** (`/config/config.yaml`)
```yaml
offline_mode: false
providers:
  openai:
    enabled: true
    model: "gpt-4o"
```

**Option B: Environment Variables** (recommended for containers)
```bash
HIVESTACK_OFFLINE_MODE=false
HIVESTACK_PROVIDERS_OPENAI_ENABLED=true
HIVESTACK_PROVIDERS_OPENAI_MODEL=gpt-4o
```

### 3. Restart

```bash
docker compose restart hivestack
# or Unraid: stop/start container
```

## Provider Reference

| Provider | Env Var | Models | Notes |
|----------|---------|--------|-------|
| **OpenAI** | `HIVESTACK_OPENAI_KEY` | gpt-4o, gpt-4o-mini, gpt-4-turbo | Requires paid account |
| **Anthropic** | `HIVESTACK_ANTHROPIC_KEY` | claude-3-5-sonnet, claude-3-opus | Requires paid account |
| **Gemini** | `HIVESTACK_GEMINI_KEY` | gemini-1.5-pro, gemini-1.5-flash | Free tier available |
| **Ollama (Local)** | (none) | llama3.1, qwen2.5, etc. | Stage 2, requires GPU |

## Switching Providers at Runtime

Via Web UI: **Settings → Providers** → toggle switches + model dropdown

Via API:
```bash
# Enable OpenAI
curl -X PATCH http://localhost:8080/api/v1/providers/openai \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "model": "gpt-4o"}'

# Disable all cloud (back to offline)
curl -X PATCH http://localhost:8080/api/v1/config \
  -H "Content-Type: application/json" \
  -d '{"offline_mode": true}'
```

## Local Ollama (Stage 2)

1. **Enable GPU profile** (docker compose):
   ```bash
   docker compose --profile gpu up -d
   ```
   Or Unraid: add `--profile gpu` to Post Arguments

2. **Enable in Settings**:
   - Provider: Ollama
   - Base URL: `http://hivestack-ollama:11434` (auto-configured)
   - Model: `llama3.1:8b` (or pull your own)

3. **First use** downloads model to `/models/ollama` (~4-8 GB)

## Security Model

- **Credentials never in config.yaml** — only env vars
- **Keys only read** when both conditions met:
  1. `offline_mode=false`
  2. `provider.enabled=true`
- **Rotate keys** by updating env var + restart (no config edit)
- **Audit trail**: provider enable/disable logged in `/data/hivestack.log`

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `403 PROVIDER_DISABLED` | offline_mode=true or provider disabled | Check both settings |
| `401 Unauthorized` | Invalid/missing API key | Verify env var set + restart |
| `429 Rate Limited` | Provider quota exceeded | Check provider dashboard |
| `504 Gateway Timeout` | Model too slow | Increase `timeout_seconds` in config |
| Model not found | Wrong model name | Check provider's model list |

## Cost Control

- **Offline mode = $0** — no cloud calls possible
- **Per-provider enable** — granular control
- **Model selection** — cheaper models (gpt-4o-mini, gemini-1.5-flash)
- **Timeout limits** — prevent runaway calls
- **Monitor usage** in provider dashboards
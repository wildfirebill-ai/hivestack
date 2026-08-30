# Getting Started with hivestack

hivestack is a **local-first AI agent platform** that runs fully offline on a Tesla M40 (Maxwell, CC 5.2).
Every outside provider (OpenAI, Anthropic, Gemini, etc.) sits behind its own **enable switch** — local-only by default.

## Quick Start (Docker Compose)

```bash
# 1. Clone the repo
git clone https://github.com/wildfirebill-ai/hivestack.git
cd hivestack

# 2. Copy env template and set a strong admin password
cp .env.example .env
# Edit .env and change HIVESTACK_ADMIN_PASSWORD=changeme

# 3. Start the stack (CPU-only, no GPU needed for Stage 1)
docker compose up -d

# 4. Open the Web UI
open http://localhost:8080
# Login: admin / your-password
```

## Quick Start (Unraid)

1. **Community Applications** → search "hivestack" → Install
2. Set **Config path**, **Data path**, **Models path** (defaults are fine)
3. Set a strong **Admin password** (required)
4. Optional: **GPU UUID(s)** — leave `all` for M40, or specify UUID
5. Click **Apply** → Web UI at `http://<unraid-ip>:8080`

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU | Tesla M40 (24GB VRAM, CC 5.2) | Same |
| Driver | NVIDIA 580 branch (Linux) | Same |
| RAM | 16 GB system + 24 GB VRAM | 32 GB + 24 GB VRAM |
| Disk | 20 GB free | 50 GB free (models + data) |
| CPU | 4 cores | 8+ cores |

**Note**: Stage 1 (core platform) runs CPU-only. Stage 2+ (local inference via Ollama) requires the M40.

## First Boot

On first start, hivestack:
1. Creates `/config/config.yaml` from defaults
2. Initializes SQLite database at `/data/hivestack.db`
3. Starts the Web UI on port 8080
4. Logs GPU detection status (or "CPU-only" if no GPU)

Check logs:
```bash
docker logs -f hivestack
```

## Next Steps

- [Configuration Reference](configuration.md) — all settings explained
- [Provider Management](providers.md) — enable cloud providers (opt-in)
- [Unraid Guide](unraid.md) — detailed Unraid setup
- [API Reference](api.md) — REST endpoints for integrations
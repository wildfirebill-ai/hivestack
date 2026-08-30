# Unraid Installation Guide

## Prerequisites

- Unraid 6.11+ (6.12+ recommended)
- **NVIDIA GPU Plugin** installed (for M40 support)
- **NVIDIA Driver 580 branch** — required for Tesla M40 (CC 5.2)
- Community Applications plugin

### Verify Driver

```bash
# On Unraid console
nvidia-smi
# Should show: Tesla M40, 24GB, CC 5.2, Driver 580.xx
```

## Install via Community Applications

1. **Apps** tab → Search "hivestack"
2. Click **Install**
3. Configure template variables (see below)
4. Click **Apply**

## Template Variables

| Variable | Default | Description |
|----------|---------|-------------|
| **Web UI Port** | `8080` | Host port for Web UI/API |
| **Config path** | `/mnt/user/appdata/hivestack/config` | Persistent config (config.yaml) |
| **Data path** | `/mnt/user/appdata/hivestack/data` | SQLite DB, logs, backups |
| **Models path** | `/mnt/user/appdata/hivestack/models` | Ollama model cache (Stage 2) |
| **Admin password** | `changeme` | **Required** — set strong password |
| **Admin user** | `admin` | Web UI username |
| **GPU UUID(s)** | `all` | NVIDIA devices to expose (`all` or UUID list) |
| **Post Arguments** | (empty) | Extra args passed to uvicorn |

### GPU UUID(s)

```bash
# Get UUIDs
nvidia-smi -L
# GPU 0: Tesla M40 (UUID: GPU-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)

# Use "all" for single GPU, or comma-separated UUIDs:
GPU-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx,GPU-yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
```

## First Boot

1. Container starts → seeds `/config/config.yaml`
2. Web UI available at `http://<unraid-ip>:8080`
3. Login: `admin` / your password

## Updating

1. **Apps** tab → **Check for Updates**
2. hivestack shows update available
3. Click **Update** → pulls new image, preserves volumes

## Stage 2: Local Inference (Ollama)

Requires M40 + NVIDIA 580 driver.

1. **Edit template** → Add **Post Arguments**: `--profile gpu`
   - Or use docker compose: `docker compose --profile gpu up -d`
2. In Web UI: **Settings → Providers → Ollama** → Enable
3. Model downloads to **Models path** on first use

## Backup / Restore

### Backup (manual)
```bash
# From Unraid console
tar -czf hivestack-backup-$(date +%F).tar.gz \
  /mnt/user/appdata/hivestack/config \
  /mnt/user/appdata/hivestack/data
```

### Restore
1. Stop container
2. Replace `/mnt/user/appdata/hivestack/` with backup
3. Start container

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "no usable nvidia-smi" | Install NVIDIA GPU Plugin + Driver 580 |
| Container won't start | Check logs: `docker logs hivestack` |
| Port 8080 in use | Change **Web UI Port** template variable |
| Permission denied on paths | Ensure `appdata` share is `cache:yes` or `cache:prefer` |
| GPU not detected | Verify `NVIDIA_VISIBLE_DEVICES=all` in template |

## Uninstall

1. Stop container
2. **Apps** → **Remove** (keeps appdata)
3. Delete `/mnt/user/appdata/hivestack/` to fully remove

## Support

- GitHub: https://github.com/wildfirebill-ai/hivestack
- Issues: https://github.com/wildfirebill-ai/hivestack/issues
- Security: security@wildfirebill.ai
# Changelog

All notable changes to hivestack are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4] - 2026-08-30

### Fixed
- Settings page crash `TypeError: x.system.slice is not a function` when prompt `system` is null — now `(p.system ?? '').slice(0,90)`
- Ollama `400 Bad Request` on chat stream now surfaces body (e.g. `model not found`) instead of generic `HTTPStatusError` → 500 stack

## [0.1.3] - 2026-08-30

### Fixed
- Dashboard GPU `not present / unknown` when `/dev/nvidia*` not injected but driver present: backend `/api/system/gpu` now falls back to `/proc/driver/nvidia/version` + device nodes, returns `present: true` with `ollama_supported: true` (CC 5.2)
- Custom `wildfire` network with static IP bypassed plugin auto `--gpus` injection — documented manual `ExtraParams: --gpus all --runtime=nvidia` workaround

## [0.1.2] - 2026-08-30

### Fixed
- GPU detection false `CPU-only`: entrypoint now detects GPU via `/dev/nvidia*` + `/proc/driver/nvidia/version` when `nvidia-smi` binary is not injected, logs `NVIDIA_VISIBLE_DEVICES` for debugging
- Unraid template: default GPU UUID set to Tesla M40 `GPU-f6160a9b-0a12-1740-5741-569d0eb02069`, added `NVIDIA_DRIVER_CAPABILITIES` variable

### Added
- Dockerfile ENV defaults for `NVIDIA_VISIBLE_DEVICES` / `NVIDIA_DRIVER_CAPABILITIES` so image works without explicit env

## [0.1.1] - 2026-08-30

### Added
- `nvidia-utils-580` in Docker image for GPU verification (`nvidia-smi` now available in container)
- Unraid template improvements: GPU UUID description with `nvidia-smi -L` hint, MaxVer extended to 7.9 (supports Unraid 7.x)
- `ca_profile.xml` for Community Apps submission compliance

### Changed
- Unraid template rewritten to dockerMan v2 Config-only format (removed legacy Networking/Data/Environment tags)
- GPU UUID default documentation improved with Tesla M40-specific guidance
- XML entities escaped (`&`) for parser compatibility

### Fixed
- GPU passthrough visibility: container now has `nvidia-smi` for verification
- Unraid template XML parsing: unescaped `&` in Overview fixed
- MaxVer updated from 6.12.9 to 7.9 (enables Unraid 7.x including 7.3.1)

## [0.1.0] - 2026-08-29

### Added
- Local-first AI agent / AIOps platform (Stages 0-11 complete).
- Provider gate with per-provider on/off switches and a global offline lockout.
- Real chat via local Ollama + cloud OpenAI/Anthropic/Gemini adapters (SSE); CPU fallback (`provider: fallback`).
- Agent runtime, scoped tool registry, sandbox, and MCP server + client.
- Workflows + scheduler, and kanban boards.
- Memory / RAG (hybrid search, temporal knowledge graph, compaction).
- Skills registry + generator, and studio (docs, data, media).
- Comms + voice, AIOps (telemetry, anomaly, RCA, remediation, chaos demo), governance, and an opt-in economy module.
- Offline end-to-end test suite (`tests/e2e_offline.py`) and backup/restore/verify tooling.

### Changed
- Anomaly detection uses a robust median/MAD z-score so isolated spikes are flagged even in bimodal series.
- An explicitly-requested cloud provider is refused (403) while offline instead of silently falling back to a local model.
- AIOps demo seeds a known-good baseline so the injected fault is reliably detected.

### Fixed
- Verified the platform against a full offline e2e run: 14/14 scenarios green.
- stdout encoding guards (UTF-8) in the e2e suite and backup tool so ex `→` / `·` never crash on cp1252 consoles.
- Agent-run `verify` gate no longer errors due to a broken relative import.

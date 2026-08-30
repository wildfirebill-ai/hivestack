# Changelog

All notable changes to hivestack are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

"""Runtime settings: env-driven paths, a single YAML config (watched by git via defaults),
the provider gate primitive, and module toggles."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent  # backend/app
REPO_ROOT = PACKAGE_DIR.resolve().parents[1]  # hivestack/
DEFAULT_CONFIG = PACKAGE_DIR / "default_config.yaml"


def _in_container() -> bool:
    """True when running inside the Docker container (Linux /config + /.dockerenv)."""
    return os.getenv("HIVESTACK_IN_CONTAINER") == "1" or Path("/") .joinpath(".dockerenv").exists()
    # note: never probe Path('/config') on the host — on Windows that maps to a drive-root dir


def _resolved_dir(name: str, fallback: Path) -> Path:
    """Explicit env (e.g. HIVESTACK_CONFIG_DIR) wins; in a container use /config, /data, /models;
    otherwise fall back to local dev runtime directories."""
    env = os.getenv(f"HIVESTACK_{name.upper()}_DIR")
    if env:
        return Path(env)
    if _in_container():
        return Path(f"/{name}")
    return fallback


class Settings:
    def __init__(self) -> None:
        self.config_dir = _resolved_dir("config", REPO_ROOT / "runtime" / "config")
        self.data_dir = _resolved_dir("data", REPO_ROOT / "runtime" / "data")
        self.models_dir = _resolved_dir("models", REPO_ROOT / "runtime" / "models")
        self.config_file = self.config_dir / "config.yaml"
        self._lock = threading.RLock()
        self.data: dict = self._load()
        self.admin_user = os.getenv("HIVESTACK_ADMIN_USER", "admin")
        self.admin_password = os.getenv("HIVESTACK_ADMIN_PASSWORD", "hivestack")

    # ------------------------------------------------------------------ load/save
    def _load(self) -> dict:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        defaults = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8")) or {}
        if not self.config_file.exists():
            with self._lock:
                self.config_file.write_text(yaml.safe_dump(defaults, sort_keys=False), encoding="utf-8")
            return defaults
        with self._lock:
            data = yaml.safe_load(self.config_file.read_text(encoding="utf-8")) or {}
        # merge so upgrades gain new module switches / registries without clobbering user edits
        merged = dict(defaults)
        for section in ("global", "server", "auth", "providers", "modules", "prompts", "mcp_servers"):
            user = (data.get(section) or {}) if isinstance(data.get(section), dict) else data.get(section)
            default = merged.get(section)
            if isinstance(default, dict) and isinstance(user, dict):
                merged[section] = {**default, **user}
            elif user is not None:
                merged[section] = user
        merged["models"] = data.get("models", defaults.get("models", []))
        return merged

    def save(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.config_file.write_text(yaml.safe_dump(self.data, sort_keys=False), encoding="utf-8")

    @property
    def name(self) -> str:
        return "hivestack"

    @property
    def version(self) -> str:
        return os.getenv("HIVESTACK_VERSION", "0.1.0")

    # ------------------------------------------------------------------ global
    @property
    def offline_mode(self) -> bool:
        return bool(self.data.get("global", {}).get("offline_mode", True))

    def set_offline_mode(self, value: bool) -> None:
        self.data.setdefault("global", {})["offline_mode"] = bool(value)
        self.save()

    @property
    def server_host(self) -> str:
        return str(self.data.get("server", {}).get("host", "0.0.0.0"))

    @property
    def server_port(self) -> int:
        return int(self.data.get("server", {}).get("port", 8080))

    # ------------------------------------------------------------------ providers
    def providers(self) -> list[dict]:
        raw = self.data.get("providers", {}) or {}
        out = []
        for name, cfg in raw.items():
            item = dict(cfg)
            item["name"] = name
            out.append(item)
        return out

    def get_provider(self, name: str) -> dict | None:
        raw = (self.data.get("providers", {}) or {}).get(name)
        if raw is None:
            return None
        item = dict(raw)
        item["name"] = name
        # allow compose to point the local engine at a service name / any host later
        override = os.getenv(f"HIVESTACK_{name.upper()}_URL")
        if override:
            item["base_url"] = override.rstrip("/")
        return item

    def set_provider_enabled(self, name: str, enabled: bool) -> dict | None:
        prov = (self.data.get("providers", {}) or {}).get(name)
        if prov is None:
            return None
        prov["enabled"] = bool(enabled)
        self.save()
        return self.get_provider(name)

    def provider_is_allowed(self, name: str) -> bool:
        """Local engines are always usable (offline mode included). Cloud providers
        require the offline switch to be OFF and their own switch ON."""
        prov = self.get_provider(name)
        if prov is None:
            return False
        if prov.get("type") == "local":
            return bool(prov.get("enabled", True))
        return (not self.offline_mode) and bool(prov.get("enabled", False))

    # ------------------------------------------------------------------ models
    @property
    def default_provider(self) -> str | None:
        return self.data.get("global", {}).get("default_provider") or None

    @property
    def default_model(self) -> str | None:
        val = self.data.get("global", {}).get("default_model")
        return None if not val else str(val)

    @property
    def infer_timeout_seconds(self) -> int:
        try:
            return int(self.data.get("global", {}).get("infer_timeout_seconds", 120))
        except (TypeError, ValueError):
            return 120

    def models(self) -> list[dict]:
        return [dict(m) for m in (self.data.get("models", []) or [])]

    def get_model(self, name: str) -> dict | None:
        for m in self.data.get("models", []) or []:
            if m.get("name", "").lower() == name.lower():
                return dict(m)
        return None

    def add_model(self, entry: dict) -> dict:
        models = self.data.get("models", []) or []
        name = entry.get("name", "").strip()
        if not name:
            raise ValueError("model needs a name")
        if any(m.get("name") == name for m in models):
            raise KeyError(f"model '{name}' already exists")
        models.append(entry)
        self.data["models"] = models
        self.save()
        return self.get_model(name)  # type: ignore[return-value]

    def remove_model(self, name: str) -> bool:
        models = self.data.get("models", []) or []
        kept = [m for m in models if m.get("name", "").lower() != name.lower()]
        if len(kept) == len(models):
            return False
        self.data["models"] = kept
        if self.default_model and self.default_model.lower() == name.lower():
            self.data.setdefault("global", {})["default_model"] = ""
        self.save()
        return True

    def set_default_model(self, provider: str, model: str | None) -> None:
        g = self.data.setdefault("global", {})
        g["default_provider"] = provider
        g["default_model"] = model or ""
        self.save()

    def set_model_enabled(self, name: str, enabled: bool) -> dict | None:
        for m in self.data.get("models", []) or []:
            if m.get("name", "").lower() == name.lower():
                m["enabled"] = bool(enabled)
                self.save()
                return dict(m)
        return None

    # ------------------------------------------------------------------ prompts
    def prompts(self) -> list[dict]:
        out = []
        for name, text in (self.data.get("prompts", {}) or {}).items():
            out.append({"name": name, "system": text})
        return out

    def get_prompt(self, name: str) -> str | None:
        return (self.data.get("prompts", {}) or {}).get(name)

    def add_prompt(self, name: str, text: str) -> None:
        prompts = self.data.setdefault("prompts", {})
        prompts[name.strip()] = text
        self.save()

    def remove_prompt(self, name: str) -> bool:
        prompts = self.data.get("prompts", {}) or {}
        if name not in prompts:
            return False
        del prompts[name]
        self.save()
        return True

    # ------------------------------------------------------------------ channels
    def channels(self) -> list[dict]:
        raw = self.data.get("channels", {}) or {}
        out = []
        for name, cfg in raw.items():
            item = dict(cfg)
            item["name"] = name
            out.append(item)
        return out

    def get_channel(self, name: str) -> dict | None:
        for ch in self.channels():
            if ch["name"] == name:
                return ch
        return None

    # ------------------------------------------------------------------ modules
    def modules(self) -> dict:
        return dict(self.data.get("modules", {}) or {})

    def module_enabled(self, name: str) -> bool:
        return bool(self.modules().get(name, False))

    def set_module_enabled(self, name: str, enabled: bool) -> bool:
        if name not in self.modules():
            raise KeyError(name)
        self.data.setdefault("modules", {})[name] = bool(enabled)
        self.save()
        return bool(self.data["modules"][name])


settings = Settings()
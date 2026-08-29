"""Dispatch + target resolution for the inference layer."""

from __future__ import annotations

from typing import Iterator

from ..config import settings
from .anthropic import AnthropicAdapter
from .base import ChatAdapter, InferenceError
from .gemini import GeminiAdapter
from .ollama import OllamaAdapter
from .openai_adapter import OpenAIAdapter

ADAPTERS: dict[str, ChatAdapter] = {
    "ollama": OllamaAdapter(),
    "openai": OpenAIAdapter(),
    "anthropic": AnthropicAdapter(),
    "gemini": GeminiAdapter(),
}


def get_adapter(provider_name: str) -> ChatAdapter:
    adapter = ADAPTERS.get(provider_name)
    if adapter is None:
        raise InferenceError(f"no inference adapter for provider '{provider_name}'", 400)
    return adapter


def _gate_required(name: str) -> None:
    """Reject a gated provider up front — cloud while offline, or disabled.

    Raises InferenceError(403) so both the chat route and the agent runtime
    surface the refusal cleanly instead of `resolve_target` silently falling
    back to a reachable local model.
    """
    prov = settings.get_provider(name)
    if prov is None:
        raise InferenceError(f"unknown provider '{name}'", 404)
    if not settings.provider_is_allowed(name):
        reason = "offline mode is on" if settings.offline_mode else "provider is disabled"
        raise InferenceError(f"provider '{name}' not allowed: {reason}", 403)


def _gate(candidate: dict) -> None:
    _gate_required(candidate["provider"])


def resolve_target(provider: str | None, model: str | None) -> tuple[dict, dict]:
    """Map a (provider, model) request onto a registered, enabled, gate-allowed pair.

    Returns (provider_config, model_entry). Raises InferenceError with a 4xx when
    nothing usable is configured.
    """
    if model:
        entry = settings.get_model(model)
        if entry is None:
            names = ", ".join(m["name"] for m in settings.models())
            raise InferenceError(f"unknown model '{model}'. registered: {names or 'none'}", 400)
        if not entry.get("enabled", True):
            raise InferenceError(f"model '{model}' is disabled in the registry", 400)
        prov_name = provider or entry.get("provider") or settings.default_provider or "ollama"
        if prov_name != entry.get("provider"):
            # keep registry authoritative when the caller guesses wrongly
            prov_name = entry["provider"]
        candidate = entry
    else:
        prov_name = (provider or settings.default_provider or "ollama").lower()
        # Gate the *requested* provider first. If a cloud provider is asked for
        # while offline (or disabled), refuse 403 now — never silently redirect
        # the call to an allowed local engine.
        _gate_required(prov_name)
        candidates = [
            m for m in settings.models()
            if m.get("provider") == prov_name and m.get("enabled", True)
        ]
        if not candidates:
            candidates = [
                m for m in settings.models()
                if m.get("enabled", True) and settings.provider_is_allowed(m.get("provider", ""))
            ]
        if not candidates:
            raise InferenceError(
                f"no enabled model on provider '{prov_name}'."
                " Add a model in Settings → Models and make sure its provider is allowed.",
                400,
            )
        candidate = candidates[0]

    # gate: local engines are always allowed; clouds need offline=off + switch on
    _gate(candidate)
    provider_cfg = settings.get_provider(candidate["provider"])
    assert provider_cfg is not None  # _gate already validated presence
    return provider_cfg, candidate


def _messages_payload(user: str, history: list[dict] | None = None) -> list[dict]:
    msgs = [dict(m) for m in (history or [])]
    msgs.append({"role": "user", "content": user})
    return msgs


def complete(
    *,
    system: str,
    messages: list[dict],
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> tuple[dict, dict]:
    """Non-streaming completion over an existing conversation (no user turn appended).
    Used by the agent runtime, which manages its own message history."""
    provider_cfg, entry = resolve_target(provider, model)
    adapter = get_adapter(provider_cfg["name"])
    result = adapter.chat(
        provider_cfg,
        entry,
        system,
        [dict(m) for m in messages],
        stream=False,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if isinstance(result, dict):
        return result, entry
    raise InferenceError("adapter returned a stream for a non-streaming call", 500)


def run_chat(
    *,
    user: str,
    provider: str | None = None,
    model: str | None = None,
    system: str = "",
    temperature: float = 0.7,
    max_tokens: int | None = None,
    history: list[dict] | None = None,
) -> tuple[dict, dict]:
    """Non-streaming chat. Returns (result, resolved_entry) where
    result = {"content": str, "usage": {input_tokens, output_tokens}}."""
    provider_cfg, entry = resolve_target(provider, model)
    adapter = get_adapter(provider_cfg["name"])
    result = adapter.chat(
        provider_cfg,
        entry,
        system,
        _messages_payload(user, history),
        stream=False,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if isinstance(result, dict):
        return result, entry
    raise InferenceError("adapter returned a stream for a non-streaming call", 500)


def stream_chat(
    *,
    user: str,
    provider: str | None = None,
    model: str | None = None,
    system: str = "",
    temperature: float = 0.7,
    max_tokens: int | None = None,
    history: list[dict] | None = None,
) -> tuple[Iterator[dict], dict]:
    """Streaming chat. Yields {"delta": str} events, ends with {"done": True, "usage": {...}}."""
    provider_cfg, entry = resolve_target(provider, model)
    adapter = get_adapter(provider_cfg["name"])
    stream = adapter.chat(
        provider_cfg,
        entry,
        system,
        _messages_payload(user, history),
        stream=True,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if not isinstance(stream, Iterator):
        raise InferenceError("adapter returned a plain result for a streaming call", 500)
    return stream, entry
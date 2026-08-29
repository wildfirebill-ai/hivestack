"""Inference layer: normalized chat adapters over local (Ollama) and cloud
(OpenAI / Anthropic / Gemini) providers, always behind the provider gate."""

from .client import InferenceError, resolve_target, run_chat, stream_chat

__all__ = ["InferenceError", "resolve_target", "run_chat", "stream_chat"]
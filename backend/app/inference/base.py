"""Shared adapter types and helpers."""

from __future__ import annotations

import os
from typing import Any, Iterator

import httpx

from ..config import settings


class InferenceError(Exception):
    """Bubbled to the API as an HTTP error."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def provider_key(provider: dict) -> str:
    key_env = provider.get("key_env") or ""
    key = os.getenv(key_env) or ""
    if not key:
        raise InferenceError(
            f"provider '{provider.get('name')}' requires API key (env {key_env or '?'}) — set it and enable the provider",
            400,
        )
    return key


def _http_timeout() -> httpx.Timeout:
    return httpx.Timeout(settings.infer_timeout_seconds)


class ChatAdapter:
    name = "base"

    def chat(
        self,
        provider: dict,
        model: dict,
        system: str,
        messages: list[dict],
        *,
        stream: bool,
        temperature: float,
        max_tokens: int | None,
    ) -> dict | Iterator[dict]:
        raise NotImplementedError

    # -- small standard transformers -------------------------------------
    @staticmethod
    def merge_same_role(msgs: list[dict]) -> list[dict]:
        out: list[dict] = []
        for m in msgs:
            if out and out[-1]["role"] == m["role"]:
                out[-1]["content"] += "\n" + m["content"]
            else:
                out.append({"role": m["role"], "content": m["content"]})
        return out

    @staticmethod
    def ensure_first_user(msgs: list[dict]) -> list[dict]:
        """Anthropic & Gemini require the conversation to open with a user turn."""
        if not msgs:
            return [{"role": "user", "content": ""}]
        if msgs[0]["role"] == "assistant":
            return [{"role": "user", "content": "\u200b"}, *msgs]
        return msgs
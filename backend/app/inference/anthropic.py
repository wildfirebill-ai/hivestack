"""Anthropic Messages API adapter (SSE streaming, system prompt separate)."""

from __future__ import annotations

import json
from typing import Any, Iterator

import httpx

from .base import ChatAdapter, InferenceError, _http_timeout, provider_key


class AnthropicAdapter(ChatAdapter):
    name = "anthropic"
    DEFAULT_MAX_TOKENS = 4096

    def _url(self, provider: dict) -> str:
        return (provider.get("base_url") or "https://api.anthropic.com/v1").rstrip("/") + "/messages"

    def _headers(self, provider: dict) -> dict[str, str]:
        return {
            "x-api-key": provider_key(provider),
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _body(
        self,
        model: dict,
        system: str,
        messages: list[dict],
        stream: bool,
        temperature: float,
        max_tokens: int | None,
    ) -> dict:
        msgs = self.ensure_first_user(self.merge_same_role(messages))
        return {
            "model": model["model_id"],
            "system": system or "",
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens or self.DEFAULT_MAX_TOKENS,
            "stream": stream,
        }

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
        url = self._url(provider)
        body = self._body(model, system, messages, stream, temperature, max_tokens)
        try:
            if stream:
                return self._stream(url, provider, body)
            with httpx.Client(timeout=_http_timeout()) as client:
                r = client.post(url, headers=self._headers(provider), json=body)
                data = _raise_for_json(r)
            return {
                "content": _join_text(data),
                "usage": {
                    "input_tokens": (data.get("usage") or {}).get("input_tokens", 0),
                    "output_tokens": (data.get("usage") or {}).get("output_tokens", 0),
                },
            }
        except httpx.HTTPError as exc:
            raise InferenceError(f"cannot reach provider 'anthropic' ({exc.__class__.__name__})") from exc

    def _stream(self, url: str, provider: dict, body: dict) -> Iterator[dict]:
        input_tokens = 0
        output_tokens = 0
        with httpx.Client(timeout=_http_timeout()) as client:
            with client.stream("POST", url, headers=self._headers(provider), json=body) as r:
                _maybe_raise_stream(r)
                for line in r.iter_lines():
                    line = line.strip()
                    if line.startswith("event:") or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    otype = obj.get("type")
                    if otype == "message_start":
                        input_tokens = (obj.get("message") or {}).get("usage", {}).get("input_tokens", 0)
                    elif otype == "content_block_delta":
                        d = obj.get("delta") or {}
                        if d.get("type") == "text_delta":
                            yield {"delta": d.get("text", "")}
                    elif otype == "message_delta":
                        output_tokens = (obj.get("usage") or {}).get("output_tokens", output_tokens)
                    elif otype == "message_stop":
                        yield {"done": True, "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}}
                        return


def _join_text(data: dict[str, Any]) -> str:
    blocks = data.get("content") or []
    return "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")


def _raise_for_json(r: httpx.Response) -> dict[str, Any]:
    try:
        data = r.json()
    except ValueError as exc:
        raise InferenceError(f"bad response from anthropic ({r.status_code}): {r.text[:200]}", 502) from exc
    if r.status_code >= 400:
        err = data.get("error", data)
        raise InferenceError(f"anthropic error {r.status_code}: {err}", r.status_code if r.status_code < 500 else 502)
    return data


def _maybe_raise_stream(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    try:
        data = r.json()
    except ValueError:
        data = r.text[:200]
    raise InferenceError(f"anthropic error {r.status_code}: {data}", r.status_code if r.status_code < 500 else 502)
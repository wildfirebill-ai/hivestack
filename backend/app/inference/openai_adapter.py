"""OpenAI-compatible chat completions adapter (OpenAI, and any compatible endpoint)."""

from __future__ import annotations

import json
from typing import Any, Iterator

import httpx

from .base import ChatAdapter, InferenceError, _http_timeout, provider_key


class OpenAIAdapter(ChatAdapter):
    name = "openai"

    def _url(self, provider: dict) -> str:
        base = (provider.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        return base + "/chat/completions"

    def _headers(self, provider: dict) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {provider_key(provider)}",
            "Content-Type": "application/json",
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
        msgs = [{"role": "system", "content": system}] if system else []
        msgs += messages
        body: dict = {"model": model["model_id"], "messages": msgs, "temperature": temperature}
        if max_tokens:
            body["max_tokens"] = max_tokens
        url = self._url(provider)
        try:
            if stream:
                body["stream"] = True
                body["stream_options"] = {"include_usage": True}
                return self._stream(url, provider, body)
            with httpx.Client(timeout=_http_timeout()) as client:
                r = client.post(url, headers=self._headers(provider), json=body)
                data = _raise_for_json(r)
            content = _message_content(data)
            usage = data.get("usage") or {}
            return {
                "content": content,
                "usage": {
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                },
            }
        except httpx.HTTPError as exc:
            raise InferenceError(f"cannot reach provider '{provider.get('name')}' ({exc.__class__.__name__})") from exc

    def _stream(self, url: str, provider: dict, body: dict) -> Iterator[dict]:
        with httpx.Client(timeout=_http_timeout()) as client:
            with client.stream("POST", url, headers=self._headers(provider), json=body) as r:
                _maybe_raise_stream(r)
                usage: dict | None = None
                for line in r.iter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        if usage:
                            yield {"done": True, "usage": usage}
                        return
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("usage"):
                        u = obj["usage"]
                        usage = {
                            "input_tokens": u.get("prompt_tokens", 0),
                            "output_tokens": u.get("completion_tokens", 0),
                        }
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0].get("delta") or {}).get("content") or ""
                    if delta:
                        yield {"delta": delta}


def _message_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise InferenceError(f"no choices in response: {data}", 502)
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if content is None:
        return ""
    return str(content)


def _raise_for_json(r: httpx.Response) -> dict[str, Any]:
    try:
        data = r.json()
    except ValueError as exc:
        raise InferenceError(f"bad response from provider ({r.status_code}): {r.text[:200]}", 502) from exc
    if r.status_code >= 400:
        detail = data.get("error", data)
        raise InferenceError(f"provider error {r.status_code}: {detail}", r.status_code if r.status_code < 500 else 502)
    return data


def _maybe_raise_stream(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    try:
        data = r.json()
    except ValueError:
        data = r.text[:200]
    raise InferenceError(f"provider error {r.status_code}: {data}", r.status_code if r.status_code < 500 else 502)
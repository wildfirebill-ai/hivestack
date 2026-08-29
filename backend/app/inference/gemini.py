"""Google Gemini (generativelanguage API) adapter."""

from __future__ import annotations

import json
from typing import Any, Iterator

import httpx

from .base import ChatAdapter, InferenceError, _http_timeout, provider_key


class GeminiAdapter(ChatAdapter):
    name = "gemini"

    def _url(self, provider: dict, model: dict, stream: bool) -> str:
        base = (provider.get("base_url") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        method = "streamGenerateContent" if stream else "generateContent"
        return f"{base}/models/{model['model_id']}:{method}"

    def _body(self, system: str, messages: list[dict]) -> dict:
        msgs = self.ensure_first_user(self.merge_same_role(messages))
        contents = []
        for m in msgs:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        body: dict[str, Any] = {"contents": contents}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        return body

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
        url = self._url(provider, model, stream)
        try:
            if stream:
                url += "?alt=sse"
                return self._stream(url, provider, system, messages)
            with httpx.Client(timeout=_http_timeout()) as client:
                r = client.post(url, params={"key": provider_key(provider)}, json=self._body(system, messages))
                data = _raise_for_json(r)
            return {
                "content": _join_parts(data),
                "usage": {
                    "input_tokens": (data.get("usageMetadata") or {}).get("promptTokenCount", 0),
                    "output_tokens": (data.get("usageMetadata") or {}).get("candidatesTokenCount", 0),
                },
            }
        except httpx.HTTPError as exc:
            raise InferenceError(f"cannot reach provider 'gemini' ({exc.__class__.__name__})") from exc

    def _stream(
        self, url: str, provider: dict, system: str, messages: list[dict]
    ) -> Iterator[dict]:
        with httpx.Client(timeout=_http_timeout()) as client:
            with client.stream(
                "POST", url, params={"key": provider_key(provider)}, json=self._body(system, messages)
            ) as r:
                _maybe_raise_stream(r)
                usage = {"input_tokens": 0, "output_tokens": 0}
                for line in r.iter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    um = obj.get("usageMetadata") or {}
                    if um.get("promptTokenCount") is not None:
                        usage["input_tokens"] = um.get("promptTokenCount", 0)
                        usage["output_tokens"] = um.get("candidatesTokenCount", 0)
                    cands = obj.get("candidates") or []
                    if cands:
                        parts = ((cands[0].get("content") or {}).get("parts")) or []
                        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
                        if text:
                            yield {"delta": text}
                    if (cands and (cands[0].get("finishReason") in ("STOP", "MAX_TOKENS"))) or obj.get("finishReason"):
                        yield {"done": True, "usage": usage}
                        return
                yield {"done": True, "usage": usage}


def _join_parts(data: dict[str, Any]) -> str:
    cands = data.get("candidates") or []
    if not cands:
        return ""
    parts = ((cands[0].get("content") or {}).get("parts")) or []
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict))


def _raise_for_json(r: httpx.Response) -> dict[str, Any]:
    try:
        data = r.json()
    except ValueError as exc:
        raise InferenceError(f"bad response from gemini ({r.status_code}): {r.text[:200]}", 502) from exc
    if r.status_code >= 400:
        raise InferenceError(f"gemini error {r.status_code}: {data}", r.status_code if r.status_code < 500 else 502)
    return data


def _maybe_raise_stream(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    try:
        data = r.json()
    except ValueError:
        data = r.text[:200]
    raise InferenceError(f"gemini error {r.status_code}: {data}", r.status_code if r.status_code < 500 else 502)
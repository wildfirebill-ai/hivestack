"""Ollama adapter — native /api/chat JSON + NDJSON streaming.
Target: Tesla M40 (CC 5.2) via the Stage 2 sidecar."""

from __future__ import annotations

import json
from typing import Any, Iterator

import httpx

from .base import ChatAdapter, InferenceError, _http_timeout


class OllamaAdapter(ChatAdapter):
    name = "ollama"

    def _url(self, provider: dict) -> str:
        return (provider.get("base_url") or "http://127.0.0.1:11434").rstrip("/") + "/api/chat"

    def _payload(
        self,
        model: dict,
        system: str,
        messages: list[dict],
        stream: bool,
        temperature: float,
        max_tokens: int | None,
    ) -> dict:
        msgs = [{"role": "system", "content": system}] if system else []
        msgs += messages
        options = {"temperature": temperature}
        if max_tokens:
            options["num_predict"] = max_tokens
        return {"model": model["model_id"], "messages": msgs, "stream": stream, "options": options}

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
        payload = self._payload(model, system, messages, stream, temperature, max_tokens)
        try:
            if stream:
                return self._stream(url, payload)
            with httpx.Client(timeout=_http_timeout()) as client:
                r = client.post(url, json=payload)
                data = _raise_for_json(r)
            msg = data.get("message", {})
            return {
                "content": msg.get("content", ""),
                "usage": {
                    "input_tokens": data.get("prompt_eval_count", 0),
                    "output_tokens": data.get("eval_count", 0),
                },
            }
        except httpx.HTTPError as exc:
            raise InferenceError(
                f"cannot reach Ollama at {url} — is the engine running? ({exc.__class__.__name__})"
            ) from exc

    def _stream(self, url: str, payload: dict) -> Iterator[dict]:
        with httpx.Client(timeout=_http_timeout()) as client:
            with client.stream("POST", url, json=payload) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("error"):
                        raise InferenceError(str(obj["error"]), 502)
                    content = ((obj.get("message") or {}).get("content")) or ""
                    done = bool(obj.get("done"))
                    usage = {
                        "input_tokens": obj.get("prompt_eval_count", 0),
                        "output_tokens": obj.get("eval_count", 0),
                    }
                    if done:
                        yield {"done": True, "usage": usage}
                        return
                    if content:
                        yield {"delta": content}


def _raise_for_json(r: httpx.Response) -> dict[str, Any]:
    try:
        data = r.json()
    except ValueError as exc:
        raise InferenceError(f"bad response from Ollama: {r.text[:200]}", 502) from exc
    if r.status_code >= 400:
        raise InferenceError(f"Ollama error {r.status_code}: {data}", r.status_code if r.status_code < 500 else 502)
    return data
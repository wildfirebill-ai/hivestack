"""Skill generator — deterministic template path (works offline) with an
optional LLM authoring path when a model is reachable."""

from __future__ import annotations

import json
import re

from . import store


def _slug_name(text: str, name: str | None) -> str:
    if name and name.strip():
        return store._slug(name)
    return store._slug(text.split("\n")[0])


def generate_template(name: str, description: str) -> dict:
    """Turn a plain-language description into a structured skill, offline."""
    clean = description.strip()
    first = clean.split("\n")[0][:160]
    extra = clean[len(first):].strip()
    instructions = (
        "You are applying a skill.\n\n"
        f"Goal area: {first}\n"
        + (f"\nContext: {extra[:1500]}\n" if extra else "")
        + "\nProcedure:\n"
        "1. Clarify the task and constraints before acting.\n"
        "2. Break the work into concrete, verifiable steps and use the tools available.\n"
        "3. Produce a concrete deliverable (file, report, summarized answer, or structured output).\n"
        "4. Verify the result yourself with available tools (read back files, run checks).\n"
        "5. Report concisely: what you did, the result, and anything blocked."
    )
    return store.add_skill(name, first, instructions, tags=["generated"])


def _parse_llm_json(text: str) -> dict | None:
    t = text.strip()
    if t.startswith("{"):
        try:
            obj = json.loads(t)
            if "instructions" in obj:
                return obj
        except json.JSONDecodeError:
            pass
    for m in re.finditer(r"```json\s*\n?(\{.*?\})\s*```", t, re.S):
        try:
            obj = json.loads(m.group(1))
            if "instructions" in obj:
                return obj
        except json.JSONDecodeError:
            continue
    return None


def generate(name: str, description: str, use_llm: bool = True) -> dict:
    slug = _slug_name(description, name)
    if not use_llm:
        return generate_template(slug, description)

    from ..config import settings
    from ..inference.base import InferenceError
    from ..inference.client import complete

    prompt = (
        "You are a skill author. Write a reusable agent skill from this description.\n"
        f"DESCRIPTION: {description[:4000]}\n"
        "Return ONLY JSON: {\"name\": \"snake_case\", \"description\": \"one line\", "
        "\"instructions\": \"<detailed, actionable procedure>\"}. "
        "The instructions should be >=120 characters and tell an agent exactly how to perform the skill."
    )
    try:
        result, _entry = complete(system="You write concise, actionable agent skills.",
                                  messages=[{"role": "user", "content": prompt}], max_tokens=900)
        obj = _parse_llm_json(result["content"]) or {}
        return store.add_skill(
            str(obj.get("name") or slug),
            str(obj.get("description") or description[:160]),
            str(obj.get("instructions") or ""),
            tags=["generated", "llm"],
        )
    except InferenceError:
        return generate_template(slug, description)
"""Context engine — estimate token budgets and pack retrieved content so prompts
stay within a window without silently dropping key sources."""

from __future__ import annotations

from . import store


def token_count(text: str) -> int:
    return max(1, (len(text or "") + 3) // 4)


def pack(results: list[dict], budget_tokens: int = 1600) -> tuple[list[str], int]:
    """Returns (formatted lines that fit the budget, dropped_count)."""
    lines: list[str] = []
    used = 0
    dropped = 0
    for r in results:
        line = f"- [{r.get('title', '')}] (scope={r.get('scope', '')}) {r.get('snippet', r.get('content', ''))[:340]}"
        cost = token_count(line) + 1
        if used + cost > budget_tokens and lines:
            dropped += 1
            continue
        lines.append(line)
        used += cost
    return lines, dropped


def retrieve_context(query: str, scope: str | None = None, k: int = 4, budget_tokens: int = 1600) -> dict:
    results = store.retrieve(query, scope, k=k)
    lines, dropped = pack(results, budget_tokens)
    return {"lines": lines, "dropped": dropped, "count": len(results)}
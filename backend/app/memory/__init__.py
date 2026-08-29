from . import context, embed, store

# expose a memory_search tool to the agent runtime (offline-safe)
from ..agents.tools import ToolDef, registry as _registry


def _memory_tool(args: dict) -> str:
    query = str(args.get("query", ""))
    k = int(args.get("k", 4) or 4)
    scope = args.get("scope") or None
    if not query:
        return "[error] query required"
    results = store.retrieve(query, scope=scope, k=k)
    if not results:
        return "(no memory matches)"
    lines = [f"- {r['title']} (scope={r['scope']}, score={r['score']}): {r['snippet']}" for r in results]
    return "\n".join(lines)


_registry.register(
    ToolDef(
        name="memory_search",
        desc="Search the persistent memory/knowledge store (notes, ingested docs, facts).",
        args_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "what to look up"},
                "k": {"type": "integer", "description": "number of results (default 4)"},
                "scope": {"type": "string", "description": "optional scope filter"},
            },
            "required": ["query"],
        },
        scope="low",
        fn=_memory_tool,
    ),
)

__all__ = ["context", "embed", "store", "retrieve_context"]

retrieve_context = context.retrieve_context
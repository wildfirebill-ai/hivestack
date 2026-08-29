"""hivestack's own MCP server — lets external MCP clients call hivestack.

Run:  python -m app.mcp_server_entry  (stdio transport)
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from .agents.runtime import create, start, task_detail
from .agents.tools import registry
from .config import settings
from .gpu import detect as gpu_detect
from .inference import run_chat

mcp = FastMCP("hivestack")


@mcp.tool()
def system_info() -> dict:
    """hivestack system info (version, offline mode)."""
    return {
        "name": settings.name,
        "version": settings.version,
        "offline_mode": settings.offline_mode,
        "default_provider": settings.default_provider,
        "default_model": settings.default_model,
    }


@mcp.tool()
def gpu_info() -> dict:
    """GPU detection via nvidia-smi."""
    return gpu_detect()


@mcp.tool()
def tool_list() -> list[dict]:
    """List the tools available to hivestack agents."""
    return [
        {"name": t.name, "description": t.desc, "scope": t.scope, "network": t.requires_network}
        for t in registry.all()
    ]


@mcp.tool()
def chat(message: str, model: str | None = None, system: str = "") -> str:
    """Send a single chat message through hivestack's provider gate. Returns the reply text."""
    result, _entry = run_chat(user=message, model=model, system=system)
    return result["content"]


@mcp.tool()
def run_agent(goal: str, max_steps: int = 8, model: str | None = None) -> dict:
    """Launch a bounded agent run for `goal` and wait for completion.
    Returns the run summary (including status and token use)."""
    rid = create(goal=goal, model=model, max_steps=min(int(max_steps), 40))
    start(rid)
    # poll a few times (bounded)
    detail = None
    for _ in range(30):
        import time
        time.sleep(2)
        detail = task_detail(rid)
        if detail and detail["status"] in ("completed", "error", "cancelled"):
            break
    return detail or {"id": rid, "status": "pending"}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
"""MCP client manager — connects to external MCP servers (stdio or streamable
HTTP) from the config's `mcp_servers`, lists their tools, and registers them
into the agent tool registry as network-gated tools (scope=high, blocked in
offline mode). A dedicated event loop thread keeps async sessions usable from
the sync agent runtime via run_coroutine_threadsafe.

Server-side tool surface for hivestack itself lives in `mcp_server_entry.py`.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

from .agents import tools as agent_tools
from .config import settings


class MCPManager:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._connected: dict[str, dict] = {}  # name -> {config, tools: [dict]}

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or not self._loop.is_running():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._loop.run_forever, daemon=True, name="mcp-loop")
                self._thread.start()
            return self._loop

    def submit(self, coro, timeout: float = 30):
        loop = self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        return fut.result(timeout=timeout)

    # ------------------------------------------------------------------ config
    def configured(self) -> list[dict]:
        raw = settings.data.get("mcp_servers", {}) or {}
        out = []
        for name, cfg in raw.items():
            item = dict(cfg)
            item["name"] = name
            item["connected"] = name in self._connected
            out.append(item)
        return out

    def get_config(self, name: str) -> dict | None:
        raw = settings.data.get("mcp_servers", {}) or {}
        cfg = raw.get(name)
        if cfg is None:
            return None
        item = dict(cfg)
        item["name"] = name
        return item

    # ------------------------------------------------------------------ connect/list
    async def _list_tools(self, cfg: dict) -> list[dict]:
        if cfg.get("url"):
            async with streamable_http_client(cfg["url"]) as (read, write):
                async with ClientSession(read, write) as sess:
                    await sess.initialize()
                    res = await sess.list_tools()
                    return [{"name": t.name, "description": t.description or "", "schema": t.inputSchema or {}} for t in res.tools]
        params = StdioServerParameters(command=cfg.get("command", ""), args=cfg.get("args") or [], env=cfg.get("env") or None)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as sess:
                await sess.initialize()
                res = await sess.list_tools()
                return [{"name": t.name, "description": t.description or "", "schema": t.inputSchema or {}} for t in res.tools]

    def connect(self, name: str) -> list[dict]:
        cfg = self.get_config(name)
        if cfg is None:
            raise LookupError(f"mcp server '{name}' not configured")
        tools = self.submit(self._list_tools(cfg), timeout=30)
        self._connected[name] = {"config": cfg, "tools": tools}
        for t in tools:
            fn = _make_external_caller(self, name, t["name"])
            agent_tools.registry.register(
                agent_tools.ToolDef(
                    name=f"{name}.{t['name']}",
                    desc=f"external MCP tool '{t['name']}' from server '{name}': {t.get('description', '')}",
                    args_schema=t.get("schema") or {"type": "object", "properties": {}},
                    scope="high",
                    requires_network=True,
                    fn=fn,
                )
            )
        return tools

    def disconnect(self, name: str) -> None:
        if name in self._connected:
            prefix = f"{name}."
            for tool in [t for t in agent_tools.registry.all() if t.name.startswith(prefix)]:
                agent_tools.registry.remove(tool.name)
            del self._connected[name]

    def connected(self) -> list[dict]:
        out = []
        for name, state in self._connected.items():
            out.append({"name": name, "tools": [t["name"] for t in state["tools"]]})
        return out


def _result_text(res) -> str:
    try:
        parts = []
        for c in res.content or []:
            if isinstance(c, TextContent):
                parts.append(c.text)
            else:
                parts.append(str(getattr(c, "text", "") or ""))
        text = "\n".join(p for p in parts if p)
        return (text or "(no output)")[:4000]
    except Exception:  # noqa: BLE001
        return "(could not decode tool result)"


def _make_external_caller(manager: MCPManager, server: str, tool: str):
    cfg_key = server

    def caller(args: dict) -> str:
        async def inv():
            cfg = manager.get_config(cfg_key)
            if cfg is None:
                return "(mcp server gone)"
            if cfg.get("url"):
                async with streamable_http_client(cfg["url"]) as (read, write):
                    async with ClientSession(read, write) as sess:
                        await sess.initialize()
                        res = await sess.call_tool(tool, arguments=args or {})
                        return _result_text(res)
            params = StdioServerParameters(command=cfg.get("command", ""), args=cfg.get("args") or [], env=cfg.get("env") or None)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as sess:
                    await sess.initialize()
                    res = await sess.call_tool(tool, arguments=args or {})
                    return _result_text(res)

        try:
            return manager.submit(inv(), timeout=60)
        except concurrent.futures.TimeoutError:
            return "(mcp call timed out)"
        except Exception as exc:  # noqa: BLE001
            return f"(mcp call failed: {exc})"

    return caller


manager = MCPManager()
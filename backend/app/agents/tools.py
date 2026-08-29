"""Tool registry with permission scopes + built-in tools.

Scopes: low (harmless), medium (workspace file ops), high (shell / network).
Network tools are refused in offline mode (provider gate for tools).
External MCP tools register here at runtime with scope=high + network."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from . import sandbox

ToolFn = Callable[[dict], str]


@dataclass
class ToolDef:
    name: str
    desc: str
    args_schema: dict
    scope: str = "medium"
    requires_network: bool = False
    timeout: int = 15
    fn: ToolFn | None = None
    extra_prompt: str = ""


class ToolRegistry:
    _BUILTIN = 0
    _EXTERNAL = 1

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef, external: bool = False) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def all(self) -> list[ToolDef]:
        return list(self._tools.values())

    def remove(self, name: str) -> bool:
        return self._tools.pop(name, None) is not None


registry = ToolRegistry()


# ------------------------------------------------------------------ argument shims
def _arg(args: dict, schema: dict, key: str, default: Any = None) -> Any:
    val = args.get(key, default)
    stype = schema.get("properties", {}).get(key, {}).get("type")
    if stype == "string" and val is not None:
        val = str(val)
    elif stype == "integer" and val is not None:
        val = int(val)
    elif stype == "number" and val is not None:
        val = float(val)
    return val


# ------------------------------------------------------------------ tools
def _tool_calc(args: dict) -> str:
    expr = _arg(args, _CALC_ARGS, "expression", "")
    try:
        return "= " + str(sandbox.safe_calc(expr))
    except ValueError as exc:
        return f"[error] {exc}"


def _tool_shell(args: dict) -> str:
    cmd = _arg(args, _SHELL_ARGS, "command", "")
    timeout = int(_arg(args, _SHELL_ARGS, "timeout", 15) or 15)
    return sandbox.run_shell(cmd, timeout=min(max(timeout, 1), 30))


def _tool_read(args: dict) -> str:
    path = _arg(args, _READ_ARGS, "path", "")
    try:
        return sandbox.read_file(path)
    except Exception as exc:
        return f"[error] {exc}"


def _tool_write(args: dict) -> str:
    path = _arg(args, _WRITE_ARGS, "path", "")
    content = _arg(args, _WRITE_ARGS, "content", "")
    try:
        return sandbox.write_file(path, content)
    except Exception as exc:
        return f"[error] {exc}"


def _tool_ls(args: dict) -> str:
    path = _arg(args, _LS_ARGS, "path", "")
    try:
        return sandbox.list_workspace(path)
    except Exception as exc:
        return f"[error] {exc}"


def _tool_web(args: dict) -> str:
    url = _arg(args, _WEB_ARGS, "url", "")
    if not url.startswith(("http://", "https://")):
        return "[error] only http(s) URLs allowed"
    try:
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            r = client.get(url)
        body = r.text[:4000]
        return f"status {r.status_code}\n{body}"
    except httpx.HTTPError as exc:
        return f"[error] fetch failed: {exc}"


_CALC_ARGS = {"type": "object", "properties": {"expression": {"type": "string", "description": "math expression"}}, "required": ["expression"]}
_SHELL_ARGS = {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer", "description": "seconds, 1-30"}}, "required": ["command"]}
_READ_ARGS = {"type": "object", "properties": {"path": {"type": "string", "description": "path relative to workspace"}}, "required": ["path"]}
_WRITE_ARGS = {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}
_LS_ARGS = {"type": "object", "properties": {"path": {"type": "string", "description": "dir relative to workspace (empty = root)"}}}
_WEB_ARGS = {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}


def _register_builtins() -> None:
    registry.register(ToolDef("calculator", "Evaluate a safe numeric math expression.", _CALC_ARGS, scope="low", fn=_tool_calc))
    registry.register(ToolDef("read_file", "Read a text file inside the workspace.", _READ_ARGS, scope="medium", fn=_tool_read))
    registry.register(ToolDef("write_file", "Write text to a file inside the workspace.", _WRITE_ARGS, scope="medium", fn=_tool_write))
    registry.register(ToolDef("list_workspace", "List files/dirs inside the workspace.", _LS_ARGS, scope="low", fn=_tool_ls))
    registry.register(ToolDef("shell", "Run a shell command in the workspace (env isolated, timed out).", _SHELL_ARGS, scope="high", fn=_tool_shell))
    registry.register(ToolDef("web_fetch", "Fetch a http(s) URL. Network tool.", _WEB_ARGS, scope="high", requires_network=True, fn=_tool_web))


_register_builtins()


def prompt_for_tools(tools: list[ToolDef]) -> str:
    lines = []
    for t in tools:
        props = t.args_schema.get("properties", {})
        arg_desc = ", ".join(f"{k}:{v.get('type','?')}" for k, v in props.items()) or "none"
        lines.append(f"- {t.name} — {t.desc} (scope={t.scope}, network={'y' if t.requires_network else 'n'})\n  args: {arg_desc}")
        if t.extra_prompt:
            lines.append(f"  {t.extra_prompt}")
    return "\n".join(lines)


def policy_denial(tool: ToolDef, policy: dict) -> str | None:
    """Return a denial reason, or None if the tool may execute."""
    if tool.requires_network:
        from ..config import settings as _s

        if _s.offline_mode:
            return "offline mode is on — network tools are blocked"
    allowed = policy.get("allowed_scopes") or []
    if tool.scope not in allowed:
        return f"scope '{tool.scope}' is not allowed for this run (allowed: {allowed or 'none'})"
    if policy.get("auto") == "ask" and tool.scope == "high":
        return "high-risk tool requires human approval (approval UI arrives with governance)"
    return None


def execute_tool(tool: ToolDef, args: dict, policy: dict) -> tuple[str, str | None]:
    """Returns (output_text, error_text_or_None)."""
    error = policy_denial(tool, policy)
    if error:
        return f"tool '{tool.name}' denied: {error}", error
    try:
        if tool.fn is None:
            return "[error] tool has no executor", "[error] tool has no executor"
        return tool.fn(args), None
    except Exception as exc:  # noqa: BLE001
        return f"[error] {exc}", str(exc)
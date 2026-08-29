"""External MCP server management — configure in config.yaml `mcp_servers`,
connect here to register their tools for agents."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import security
from ..mcp_manager import manager

router = APIRouter(prefix="/api/mcp", tags=["mcp"])
_auth = Depends(security.require_token)


@router.get("/servers")
def list_servers(_: str = _auth) -> dict:
    return {"servers": manager.configured()}


@router.post("/servers/{name}/connect")
def connect_server(name: str, _: str = _auth) -> dict:
    try:
        tools = manager.connect(name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"connect failed: {exc}") from None
    return {"connected": name, "tools": [t["name"] for t in tools]}


@router.post("/servers/{name}/disconnect")
def disconnect_server(name: str, _: str = _auth) -> dict:
    manager.disconnect(name)
    return {"disconnected": name}


@router.get("/connected")
def connected_servers(_: str = _auth) -> dict:
    return {"connected": manager.connected()}
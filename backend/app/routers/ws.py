"""WebSocket gateway (echo stub in Stage 1; becomes the agent event stream)."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            data = await ws.receive_text()
            await ws.send_text(f"hivestack-echo: {data}")
    except Exception:  # client disconnected
        await ws.close()
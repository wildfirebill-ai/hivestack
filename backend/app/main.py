"""FastAPI application factory. Features register on the bus via routers;
static web assets are served when a build exists."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import init_db
from .routers import agents, aiops, auth, boards, chat, comms, economy, governance, health, memory, models, mcp, prompts, skills, studio, system, workflows, ws
from .workflows import scheduler as workflow_scheduler


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    init_db()
    workflow_scheduler.start()
    yield
    workflow_scheduler.stop()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.name, version=settings.version, lifespan=_lifespan)

    # Dev conveniences only; production behind the Unraid container is same-origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(system.router)
    app.include_router(models.router)
    app.include_router(prompts.router)
    app.include_router(chat.router)
    app.include_router(agents.router)
    app.include_router(memory.router)
    app.include_router(skills.router)
    app.include_router(studio.router)
    app.include_router(comms.router)
    app.include_router(aiops.router)
    app.include_router(governance.router)
    app.include_router(economy.router)
    app.include_router(economy.public_router)
    app.include_router(workflows.router)
    app.include_router(boards.router)
    app.include_router(mcp.router)
    app.include_router(ws.router)

    # Serve a built Web UI (baked into the image at hivestack/web/dist).
    owned_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    baked_dist = Path("/app/web/dist")
    web_dist = baked_dist if baked_dist.exists() else owned_dist
    if web_dist.exists():
        app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="web")

    return app


app = create_app()
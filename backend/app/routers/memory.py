"""Memory & knowledge endpoints."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from .. import security
from ..config import settings
from ..memory import context as _ctx
from ..memory import embed, store

router = APIRouter(prefix="/api/memory", tags=["memory"])
_auth = Depends(security.require_token)


def _require_module() -> None:
    if not settings.module_enabled("memory"):
        raise HTTPException(status_code=403, detail="memory module is disabled")


class NoteIn(BaseModel):
    scope: str = "global"
    title: str
    kind: str = "note"
    content: str
    tags: list[str] | None = None


class IngestIn(BaseModel):
    source_type: str = "text"  # text | csv | url
    title: str
    scope: str = "global"
    content: str = ""
    url: str = ""


class SearchIn(BaseModel):
    query: str
    scope: str | None = None
    k: int = 5
    include_archived: bool = False


class CompactIn(BaseModel):
    scope: str = "global"


class EntityIn(BaseModel):
    name: str
    scope: str = "global"
    kind: str = "entity"


class LinkIn(BaseModel):
    source: str
    relation: str
    target: str
    scope: str = "global"


@router.get("")
def overview(_: str = _auth) -> dict:
    return {
        "embeddings": embed.available(),
        "embed_model": "all-MiniLM-L6-v2" if embed.available() else None,
    }


@router.get("/notes")
def notes(scope: str | None = None, include_archived: bool = False, _: str = _auth) -> dict:
    return {"notes": store.list_notes(scope=scope, include_archived=include_archived)}


@router.get("/notes/{note_id}")
def note_detail(note_id: int, _: str = _auth) -> dict:
    n = store.get_note(note_id)
    if n is None:
        raise HTTPException(status_code=404, detail="note not found")
    return {"note": n}


@router.post("/notes")
def create_note(body: NoteIn, _: str = _auth) -> dict:
    _require_module()
    note_id = store.add_note(body.title, body.content, body.scope, body.kind, body.tags)
    return {"note_id": note_id}


@router.delete("/notes/{note_id}")
def delete_note(note_id: int, _: str = _auth) -> dict:
    if not store.delete_note(note_id):
        raise HTTPException(status_code=404, detail="note not found")
    return {"removed": note_id}


@router.post("/search")
def search(body: SearchIn, _: str = _auth) -> dict:
    results = store.search(body.query, scope=body.scope, k=body.k, include_archived=body.include_archived)
    return {"results": results}


@router.get("/retrieve")
def retrieve(q: str, scope: str | None = None, k: int = 4, _: str = _auth) -> dict:
    results = store.retrieve(q, scope=scope, k=k)
    return {"results": results, "context": _ctx.retrieve_context(q, scope=scope, k=k)}


@router.post("/ingest")
def ingest(body: IngestIn, _: str = _auth) -> dict:
    _require_module()
    stype = body.source_type
    if stype == "url":
        if settings.offline_mode:
            raise HTTPException(status_code=403, detail="url ingest is a network call — offline mode is on")
        import httpx

        try:
            with httpx.Client(timeout=20, follow_redirects=True) as client:
                r = client.get(body.url)
            content = r.text[:200000]
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"fetch failed: {exc}") from None
    elif stype == "csv":
        try:
            rows = list(csv.reader(io.StringIO(body.content)))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=f"bad csv: {exc}") from None
        content = "\n".join([" | ".join(row) for row in rows[:2000]])
    else:
        content = body.content
    note_id = store.add_document(body.title, content, scope=body.scope, kind="doc")
    return {"note_id": note_id, "chars": len(content)}


@router.post("/ingest/file")
async def ingest_file(file: UploadFile, scope: str = "global", title: str | None = None, _: str = _auth) -> dict:
    _require_module()
    raw = await file.read()
    try:
        content = raw.decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"decode failed: {exc}") from None
    name = title or (file.filename or "upload")
    note_id = store.add_document(name, content, scope=scope, kind="doc")
    return {"note_id": note_id, "chars": len(content), "filename": file.filename}


@router.post("/compact")
def compact(body: CompactIn, _: str = _auth) -> dict:
    return store.compact(scope=body.scope)


@router.post("/archive/{note_id}")
def archive(note_id: int, archived: bool = True, _: str = _auth) -> dict:
    if not store.set_archived(note_id, archived):
        raise HTTPException(status_code=404, detail="note not found")
    return {"note_id": note_id, "archived": archived}


# ------------------------------------------------------------------ knowledge graph
@router.get("/kb")
def knowledge_base(scope: str | None = None, _: str = _auth) -> dict:
    return store.knowledge_base(scope=scope)


@router.post("/entities")
def create_entity(body: EntityIn, _: str = _auth) -> dict:
    eid = store.add_entity(body.name, body.scope, body.kind)
    return {"entity_id": eid}


@router.post("/links")
def create_link(body: LinkIn, _: str = _auth) -> dict:
    lid = store.add_link(body.source, body.relation, body.target, body.scope)
    return {"link_id": lid}


@router.post("/links/{link_id}/invalidate")
def invalidate(link_id: int, _: str = _auth) -> dict:
    if not store.invalidate_link(link_id):
        raise HTTPException(status_code=404, detail="link not found")
    return {"link_id": link_id, "active": False}
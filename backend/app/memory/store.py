"""Memory & knowledge store — verbatim notes + chunks, hybrid search
(semantic via CPU embeddings + keyword via FTS5/LIKE), RAG ingest, and a
lightweight temporal knowledge graph. Originals are never deleted; compaction
merges similar notes into summaries and archives the sources."""

from __future__ import annotations

import json
import re
import time

import numpy as np

from ..db import _conn
from . import embed

_FTS_OK = True

_STOP = set(
    "a an and are as at be by for from in is it of on or that the this to with was were will would".split()
)


def _tok(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-zA-Z0-9_]{2,}", (text or "").lower()) if w not in _STOP]


def _chunkify(content: str, size: int = 1400, overlap: int = 200) -> list[str]:
    def split_piece(piece: str) -> list[str]:
        """Split an over-long piece on word boundaries."""
        words = piece.split(" ")
        out: list[str] = []
        buf = ""
        for w in words:
            if len(buf) + len(w) + 1 > size and buf:
                out.append(buf.strip())
                buf = w
            else:
                buf += (" " + w) if buf else w
        if buf.strip():
            out.append(buf.strip())
        return out

    if len(content) <= size:
        return [content]
    parts = re.split(r"(?<=\n)", content)
    chunks: list[str] = []
    buf = ""
    for p in parts:
        if len(buf) + len(p) > size and buf:
            chunks.append(buf)
            buf = ""
        if len(p) > size:
            if buf:
                chunks.append(buf)
                buf = ""
            for piece in split_piece(p):
                if piece:
                    chunks.append(piece[:size])
            continue
        buf += p
    if buf.strip():
        chunks.append(buf.strip())
    return [c for c in chunks if c.strip()]


# ------------------------------------------------------------------ fts helpers
def _fts_insert(chunk_id: int, content: str) -> None:
    global _FTS_OK
    if not _FTS_OK:
        return
    try:
        with _conn() as con:
            con.execute("INSERT INTO memory_fts(rowid, content) VALUES (?,?)", (chunk_id, content))
    except Exception:  # noqa: BLE001
        _FTS_OK = False


def _fts_delete(chunk_id: int) -> None:
    global _FTS_OK
    if not _FTS_OK:
        return
    try:
        with _conn() as con:
            con.execute("DELETE FROM memory_fts WHERE rowid=?", (chunk_id,))
    except Exception:  # noqa: BLE001
        _FTS_OK = False


def _fts_search(query: str) -> list[tuple[int, float]]:
    """Returns [(chunk_id, bm25ish_score)] ordered by relevance."""
    if not _FTS_OK:
        return []
    try:
        with _conn() as con:
            rows = con.execute(
                "SELECT rowid, bm25(memory_fts) AS b, rank FROM memory_fts"
                ' WHERE memory_fts MATCH ? ORDER BY rank LIMIT 60',
                (query,),
            ).fetchall()
        return [(r["rowid"], float(r["b"])) for r in rows]
    except Exception:  # noqa: BLE001
        return []


def _like_search(query: str, scope: str | None, limit: int = 60) -> list[tuple[int, float]]:
    terms = _tok(query)
    if not terms:
        return []
    where = f"ar.archived=0"
    params: list = []
    if scope:
        where += " AND ar.scope=?"
        params.append(scope)
    like = " OR ".join(["c.content LIKE ?"] * len(terms))
    for t in terms:
        params.append(f"%{t}%")
    with _conn() as con:
        rows = con.execute(
            f"SELECT c.id AS cid, COUNT(*) AS hits FROM memory_chunks c"
            f" JOIN memory_notes ar ON ar.id=c.note_id WHERE {where} AND ({like})"
            f" GROUP BY c.id ORDER BY hits DESC, c.id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    return [(r["cid"], float(r["hits"])) for r in rows]


# ------------------------------------------------------------------ notes
def add_note(title: str, content: str, scope: str = "global", kind: str = "note", tags: list[str] | None = None) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO memory_notes(scope, title, kind, tags) VALUES (?,?,?,?)",
            (scope, title, kind, json.dumps(tags or [])),
        )
        note_id = cur.lastrowid
    _store_chunk(note_id, 0, content)
    return note_id


def add_document(title: str, content: str, scope: str = "global", kind: str = "doc") -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO memory_notes(scope, title, kind) VALUES (?,?,?)", (scope, title, kind)
        )
        note_id = cur.lastrowid
    for i, piece in enumerate(_chunkify(content)):
        _store_chunk(note_id, i, piece)
    return note_id


def _store_chunk(note_id: int, ordinal: int, content: str) -> int:
    vec = embed.embed_one(content)
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO memory_chunks(note_id, ordinal, content, embedding) VALUES (?,?,?,?)",
            (note_id, ordinal, content, json.dumps(vec) if vec else None),
        )
        cid = cur.lastrowid
    _fts_insert(cid, content)
    return cid


def get_note(note_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM memory_notes WHERE id=?", (note_id,)).fetchone()
    if row is None:
        return None
    note = dict(row)
    with _conn() as con:
        chunks = con.execute("SELECT id, ordinal, content FROM memory_chunks WHERE note_id=? ORDER BY ordinal", (note_id,)).fetchall()
    note["chunks"] = [dict(c) for c in chunks]
    return note


def delete_note(note_id: int) -> bool:
    with _conn() as con:
        ids = [r["id"] for r in con.execute("SELECT id FROM memory_chunks WHERE note_id=?", (note_id,)).fetchall()]
        con.execute("DELETE FROM memory_chunks WHERE note_id=?", (note_id,))
        cur = con.execute("DELETE FROM memory_notes WHERE id=?", (note_id,))
    for cid in ids:
        _fts_delete(cid)
    return cur.rowcount > 0


def set_archived(note_id: int, archived: bool) -> bool:
    with _conn() as con:
        cur = con.execute("UPDATE memory_notes SET archived=?, updated_at=datetime('now') WHERE id=?", (int(archived), note_id))
    return cur.rowcount > 0


def list_notes(scope: str | None = None, include_archived: bool = False, limit: int = 200) -> list[dict]:
    where = "1=1"
    params: list = []
    if scope:
        where += " AND scope=?"
        params.append(scope)
    if not include_archived:
        where += " AND archived=0"
    with _conn() as con:
        rows = con.execute(
            f"SELECT id, scope, title, kind, archived, tags, created_at FROM memory_notes"
            f" WHERE {where} ORDER BY created_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ search / retrieve
def _semantic_scores(query: str, chunk_ids: list[int]) -> dict[int, float]:
    if not embed.available() or not chunk_ids:
        return {}
    qv = embed.embed_one(query)
    if qv is None:
        return {}
    placeholders = ",".join("?" * len(chunk_ids))
    with _conn() as con:
        rows = con.execute(f"SELECT id, embedding FROM memory_chunks WHERE id IN ({placeholders})", chunk_ids).fetchall()
    out: dict[int, float] = {}
    for r in rows:
        raw = r["embedding"]
        if not raw:
            continue
        try:
            out[r["id"]] = embed.cos(qv, json.loads(raw))
        except (ValueError, TypeError):
            continue
    return out


def _semantic_top(query: str, scope: str | None, k: int) -> list[tuple[int, float]]:
    where = "ar.archived=0"
    params: list = []
    if scope:
        where += " AND ar.scope=?"
        params.append(scope)
    with _conn() as con:
        rows = con.execute(
            f"SELECT c.id AS cid, c.embedding FROM memory_chunks c JOIN memory_notes ar ON ar.id=c.note_id"
            f" WHERE {where} AND c.embedding IS NOT NULL ORDER BY c.id DESC LIMIT 2000",
            params,
        ).fetchall()
    qv = embed.embed_one(query)
    if qv is None:
        return []
    scored: list[tuple[int, float]] = []
    for r in rows:
        try:
            scored.append((r["cid"], embed.cos(qv, json.loads(r["embedding"]))))
        except (ValueError, TypeError):
            continue
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]


def search(query: str, scope: str | None = None, k: int = 5, include_archived: bool = False) -> list[dict]:
    k = min(max(int(k), 1), 20)
    kw: dict[int, float] = {}
    for cid, b in _fts_search(query):
        kw[cid] = -b  # bm25() returns negative → invert to positive relevance
    if not kw:
        for cid, hits in _like_search(query, scope, 60):
            kw[cid] = float(hits)
    cands = list(kw.keys())
    sem = _semantic_scores(query, cands) if cands else {}
    if not cands and embed.available():
        cands = [cid for cid, _s in _semantic_top(query, scope, k)]
        sem = _semantic_scores(query, cands)

    if not cands:
        return []

    scores: dict[int, float] = {}
    max_kw = max(kw.values()) if kw else 0.0
    for cid in cands:
        kwn = (kw.get(cid, 0) / max_kw) if max_kw else 0.0
        sn = sem.get(cid, 0.0)
        scores[cid] = 0.55 * kwn + 0.45 * sn if sem else kwn

    best = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
    where = "c.id IN ({}) AND ar.archived=?"
    params = [0 if not include_archived else -1]
    placeholders = ",".join("?" * len(best))
    with _conn() as con:
        rows = con.execute(
            f"SELECT c.id AS chunk_id, c.note_id, c.content, ar.title, ar.scope, ar.kind, ar.archived"
            f" FROM memory_chunks c JOIN memory_notes ar ON ar.id=c.note_id"
            f" WHERE c.id IN ({placeholders}) AND ar.archived=0",
            [cid for cid, _ in best],
        ).fetchall()
    out: list[dict] = []
    by_id = {cid: s for cid, s in best}
    for r in rows:
        d = dict(r)
        snip = d["content"][:220]
        d["snippet"] = snip
        d["score"] = round(by_id.get(r["chunk_id"], 0.0), 4)
        out.append(d)
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def retrieve(query: str, scope: str | None = None, k: int = 4) -> list[dict]:
    return search(query, scope, k=k)


# ------------------------------------------------------------------ compaction
def compact(scope: str = "global", threshold: float = 0.88) -> dict:
    if not embed.available():
        return {"merged": 0, "reason": "embeddings unavailable — install fastembed model cache"}
    with _conn() as con:
        rows = con.execute(
            "SELECT n.id, n.title, c.content, c.embedding FROM memory_notes n"
            " JOIN memory_chunks c ON c.note_id=n.id"
            " WHERE n.archived=0 AND n.kind != 'summary' AND n.scope=? AND c.embedding IS NOT NULL",
            (scope,),
        ).fetchall()
    notes: list[dict] = []
    for r in rows:
        try:
            v = np.asarray(json.loads(r["embedding"]), dtype=np.float32)
        except (ValueError, TypeError):
            continue
        notes.append({"id": r["id"], "title": r["title"], "content": r["content"], "vec": v})
    if len(notes) < 2:
        return {"merged": 0}

    assigned: list[int] = []
    merged = 0
    for i in range(len(notes)):
        if i in assigned:
            continue
        cluster = [i]
        assigned.append(i)
        for j in range(i + 1, len(notes)):
            if j in assigned:
                continue
            if _cos(notes[i]["vec"], notes[j]["vec"]) >= threshold:
                cluster.append(j)
                assigned.append(j)
        if len(cluster) <= 1:
            continue
        merged += 1
        body = "\n\n---\n\n".join(f"{notes[mi]['title']}\n{notes[mi]['content']}" for mi in cluster)
        summary_id = add_document(
            title=f"summary #{merged} ({scope})",
            content=body,
            scope=scope,
            kind="summary",
        )
        for mi in cluster:
            set_archived(notes[mi]["id"], True)
    return {"merged": merged}


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    return float(np.dot(a, b) / (na * nb)) if na and nb else 0.0


# ------------------------------------------------------------------ knowledge graph
def add_entity(name: str, scope: str = "global", kind: str = "entity") -> int:
    with _conn() as con:
        con.execute("INSERT OR IGNORE INTO memory_entities(name, kind, scope) VALUES (?,?,?)", (name, kind, scope))
        row = con.execute("SELECT id FROM memory_entities WHERE name=? AND scope=?", (name, scope)).fetchone()
    return row["id"]  # type: ignore[index]


def entity_id(name: str, scope: str = "global") -> int | None:
    with _conn() as con:
        row = con.execute("SELECT id FROM memory_entities WHERE name=? AND scope=?", (name, scope)).fetchone()
    return row["id"] if row else None  # type: ignore[union-attr]


def add_link(source: str, relation: str, target: str, scope: str = "global", valid_from: str | None = None) -> int:
    s = add_entity(source, scope)
    t = add_entity(target, scope)
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO memory_links(source_id, target_id, relation, valid_from) VALUES (?,?,?,?)",
            (s, t, relation, valid_from),
        )
    return cur.lastrowid  # type: ignore[union-attr]


def invalidate_link(link_id: int) -> bool:
    with _conn() as con:
        cur = con.execute("UPDATE memory_links SET active=0, valid_to=date('now') WHERE id=?", (link_id,))
    return cur.rowcount > 0  # type: ignore[union-attr]


def knowledge_base(scope: str | None = None) -> dict:
    with _conn() as con:
        rows = con.execute("SELECT * FROM memory_entities WHERE scope=? OR ? IS NULL ORDER BY name", (scope, scope)).fetchall()
        entities = [dict(r) for r in rows]
        link_rows = con.execute(
            "SELECT l.id, l.relation, l.valid_from, l.valid_to, l.active,"
            " s.name AS source, t.name AS target, s.scope AS scope"
            " FROM memory_links l"
            " JOIN memory_entities s ON s.id=l.source_id"
            " JOIN memory_entities t ON t.id=l.target_id"
            " WHERE l.active=1 ORDER BY l.id"
        ).fetchall()
    return {"entities": entities, "links": [dict(r) for r in link_rows]}
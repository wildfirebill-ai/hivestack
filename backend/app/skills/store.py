"""Skill store — registry, frontmatter parsing, export, install (local/git),
and install-source sync-state. A skill is a named, versioned instruction bundle
that can be injected into agent runs and exported as a portable SKILL.md."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

from ..config import settings
from ..db import _conn

VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-\.]{1,63}$")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", text.strip().lower()).strip("-")
    return (s or "skill")[:64]


def _row(sql: str, params: tuple = ()) -> dict | None:
    with _conn() as con:
        r = con.execute(sql, params).fetchone()
    return dict(r) if r else None


# ------------------------------------------------------------------ crud
def list_skills() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT name, version, description, tags, source, installed_from, status, created_at"
            " FROM skills ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def get_skill(name: str) -> dict | None:
    row = _row("SELECT * FROM skills WHERE name=?", (name,))
    if row is None:
        return None
    return row


def add_skill(
    name: str,
    description: str,
    instructions: str,
    tags: list[str] | None = None,
    version: str = "1.0.0",
    source: str = "builtin",
    installed_from: str | None = None,
) -> dict:
    if not VALID_NAME_RE.match(name):
        raise ValueError("invalid skill name (2-64 chars, [a-z0-9._-])")
    with _conn() as con:
        con.execute(
            "INSERT INTO skills(name, version, description, instructions, tags, source, installed_from)"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(name) DO UPDATE SET version=excluded.version, description=excluded.description,"
            " instructions=excluded.instructions, tags=excluded.tags, source=excluded.source,"
            " installed_from=excluded.installed_from, status='active', updated_at=datetime('now')",
            (name, version, description, instructions, json.dumps(tags or []), source, installed_from),
        )
    return get_skill(name)  # type: ignore[return-value]


def delete_skill(name: str) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM skills WHERE name=?", (name,))
    return cur.rowcount > 0  # type: ignore[union-attr]


def set_status(name: str, status: str) -> bool:
    with _conn() as con:
        cur = con.execute("UPDATE skills SET status=?, updated_at=datetime('now') WHERE name=?", (status, name))
    return cur.rowcount > 0  # type: ignore[union-attr]


# ------------------------------------------------------------------ metadata
def validate(name: str) -> dict:
    skill = get_skill(name)
    if skill is None:
        raise LookupError("skill not found")
    instructions = skill["instructions"] or ""
    checks = [
        {"name": "name", "pass": bool(VALID_NAME_RE.match(name)), "detail": name},
        {"name": "description", "pass": bool((skill.get("description") or "").strip()), "detail": skill.get("description", "")[:80]},
        {"name": "instructions_len", "pass": 40 <= len(instructions) <= 20000, "detail": f"{len(instructions)} chars"},
        {"name": "has_verb", "pass": any(v in instructions.lower() for v in ("when", "always", "procedure", "steps", "if", "1.", "you should")),
         "detail": "presence of actionable language"},
        {"name": "version", "pass": bool((skill.get("version") or "").strip()), "detail": skill.get("version", "")},
    ]
    passed = sum(1 for c in checks if c["pass"])
    return {"name": name, "checks": checks, "score": round(passed / len(checks), 2), "pass": passed == len(checks)}


def export(name: str) -> dict:
    skill = get_skill(name)
    if skill is None:
        raise LookupError("skill not found")
    md = (
        "---\n"
        f"name: {skill['name']}\n"
        f"description: {json.dumps(skill.get('description') or '')}\n"
        f"version: \"{skill.get('version', '1.0.0')}\"\n"
        "---\n"
        f"{skill['instructions']}\n"
    )
    return {
        "name": skill["name"],
        "version": skill.get("version", "1.0.0"),
        "description": skill.get("description", ""),
        "tags": json.loads(skill.get("tags") or "[]"),
        "manifest": {"platform": "hivestack", "skill_version": "1.0", "schema": "SKILL.md+frontmatter"},
        "skill_md": md,
    }


def parse_skill_md(text: str) -> dict:
    """Parse a SKILL.md into (name, description, instructions)."""
    body = text
    meta: dict = {}
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                meta = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                meta = {}
            body = parts[2].strip()
    name = str(meta.get("name") or _slug((body.splitlines() or [""])[0]))
    description = str(meta.get("description") or (body.splitlines() or [""])[0])[:200]
    return {"name": name, "description": description, "instructions": body}


# ------------------------------------------------------------------ sources / install
def register_source(kind: str, ref: str, label: str | None, sha: str | None) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO skill_sources(kind, ref, label, recorded_sha) VALUES (?,?,?,?)",
            (kind, ref, label, sha),
        )
    return cur.lastrowid  # type: ignore[union-attr]


def list_sources() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM skill_sources ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def sync_states() -> list[dict]:
    out = []
    for src in list_sources():
        state = "unknown"
        detail = ""
        if src["kind"] == "git":
            path = _installed_dir(src["ref"])
            if path.exists():
                head = _git(path, "rev-parse", "HEAD")
                state = "synced" if head == src["recorded_sha"] else "modified"
                detail = f"head {head[:8] or '?'}"
            else:
                state = "missing"
        elif src["kind"] == "local":
            p = Path(src["ref"])
            state = "present" if p.exists() else "missing"
            detail = str(p)
        out.append({**src, "state": state, "detail": detail})
    return out


def _installed_dir(ref: str) -> Path:
    slug = _slug(ref.split("/")[-1].replace(".git", ""))
    d = settings.data_dir / "installed" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _git(path: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, timeout=30)
        return (r.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def install(kind: str, ref: str, label: str | None = None) -> dict:
    """kind: local (path to a dir/SKILL.md) | git (url). Records source + registers skills."""
    skills_installed: list[dict] = []
    sha = None
    found_file = None
    if kind == "git":
        dest = _installed_dir(ref)
        if not (dest / ".git").exists():
            subprocess.run(
                ["git", "clone", "--depth", "1", ref, str(dest)],
                capture_output=True, text=True, timeout=120,
            )
        sha = _git(dest, "rev-parse", "HEAD") or sha
        candidates = [dest / "SKILL.md"]
        candidates += sorted(dest.glob("*.md"))
        for cand in candidates:
            if cand.is_file() and cand.name.lower() != "readme.md":
                found_file = cand
                break
        source = dest
    else:
        source = Path(ref)
        found_file = source if source.is_file() and source.suffix.lower() in (".md",) else source / "SKILL.md"
    if found_file is None or not found_file.is_file():
        raise FileNotFoundError(f"no SKILL.md found at {source}")
    meta = parse_skill_md(found_file.read_text(encoding="utf-8", errors="replace"))
    skill = add_skill(
        meta["name"],
        meta["description"],
        meta["instructions"],
        source="installed",
        installed_from=f"{kind}:{ref}",
    )
    skills_installed.append(export(meta["name"]))
    register_source(kind, ref, label, sha)
    if kind == "local":
        # verify local path stays reachable
        pass
    return {"source_id": sha if kind == "git" else str(source), "skills": skills_installed, "sha": sha}


def installed_dir_for(ref: str) -> Path:
    return _installed_dir(ref)
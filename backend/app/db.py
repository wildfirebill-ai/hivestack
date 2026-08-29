"""SQLite persistence (single portable file under /data)."""

from __future__ import annotations

import sqlite3

from .config import settings


def _conn() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(settings.data_dir / "hivestack.db", timeout=10)
    con.row_factory = sqlite3.Row
    # Hardened SQLite: WAL for concurrent reads + durability, FK enforcement,
    # and a busy timeout so short writer locks don't 500 under load.
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA sync_mode=NORMAL")
        con.execute("PRAGMA busy_timeout=10000")
    except sqlite3.Error:
        pass
    return con


def _column_names(con: sqlite3.Connection, table: str) -> set[str]:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _ensure_columns(con: sqlite3.Connection, table: str, cols: list[str]) -> None:
    existing = _column_names(con, table)
    for col in cols:
        if col not in existing:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col}")


def init_db() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with _conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS kv (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                role         TEXT NOT NULL,
                content      TEXT NOT NULL,
                source       TEXT,
                provider     TEXT,
                model        TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id             TEXT PRIMARY KEY,
                name           TEXT,
                goal           TEXT NOT NULL,
                template       TEXT,
                provider       TEXT,
                model          TEXT,
                status         TEXT NOT NULL DEFAULT 'queued',
                max_steps      INTEGER DEFAULT 10,
                allowed_scopes TEXT,
                policy         TEXT,
                error          TEXT,
                tokens_in      INTEGER DEFAULT 0,
                tokens_out     INTEGER DEFAULT 0,
                created_at     TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at     TEXT
            );

            CREATE TABLE IF NOT EXISTS run_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id     TEXT NOT NULL,
                seq        INTEGER NOT NULL,
                kind       TEXT NOT NULL,
                data       TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS workflows (
                id         TEXT PRIMARY KEY,
                name       TEXT,
                definition TEXT NOT NULL,
                enabled    INTEGER DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS workflow_runs (
                id          TEXT PRIMARY KEY,
                workflow_id TEXT,
                status      TEXT NOT NULL DEFAULT 'queued',
                current_step TEXT,
                context     TEXT,
                error       TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS workflow_step_runs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id        TEXT NOT NULL,
                step_id       TEXT NOT NULL,
                status        TEXT NOT NULL DEFAULT 'pending',
                attempts      INTEGER DEFAULT 0,
                output        TEXT,
                started_at    TEXT,
                finished_at   TEXT
            );

            CREATE TABLE IF NOT EXISTS schedules (
                id          TEXT PRIMARY KEY,
                workflow_id TEXT,
                kind        TEXT NOT NULL,
                value       TEXT NOT NULL,
                enabled     INTEGER DEFAULT 1,
                next_run_at TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS boards (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS board_columns (
                id       TEXT PRIMARY KEY,
                board_id TEXT NOT NULL,
                name     TEXT NOT NULL,
                position INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS board_cards (
                id         TEXT PRIMARY KEY,
                column_id  TEXT NOT NULL,
                title      TEXT NOT NULL,
                body       TEXT,
                run_id     TEXT,
                position   INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS memory_notes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                scope      TEXT NOT NULL DEFAULT 'global',
                title      TEXT NOT NULL,
                kind       TEXT NOT NULL DEFAULT 'note',
                archived   INTEGER DEFAULT 0,
                tags       TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS memory_chunks (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                note_id   INTEGER NOT NULL,
                ordinal   INTEGER DEFAULT 0,
                content   TEXT NOT NULL,
                embedding TEXT
            );

            CREATE TABLE IF NOT EXISTS memory_entities (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                name  TEXT NOT NULL,
                kind  TEXT DEFAULT 'entity',
                scope TEXT DEFAULT 'global',
                UNIQUE(name, scope)
            );

            CREATE TABLE IF NOT EXISTS memory_links (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id  INTEGER NOT NULL,
                target_id  INTEGER NOT NULL,
                relation   TEXT NOT NULL,
                valid_from TEXT,
                valid_to   TEXT,
                active     INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS skills (
                name           TEXT PRIMARY KEY,
                version        TEXT DEFAULT '1.0.0',
                description    TEXT,
                instructions   TEXT NOT NULL,
                tags           TEXT,
                source         TEXT DEFAULT 'builtin',
                installed_from TEXT,
                status         TEXT DEFAULT 'active',
                created_at     TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at     TEXT
            );

            CREATE TABLE IF NOT EXISTS skill_sources (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                kind         TEXT NOT NULL,   -- local | git
                ref          TEXT NOT NULL,
                label        TEXT,
                recorded_sha TEXT,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS documents (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                format     TEXT NOT NULL,
                path       TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS publish_jobs (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                body       TEXT,
                targets    TEXT,
                status     TEXT NOT NULL DEFAULT 'pending_approval',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS channel_messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                channel    TEXT NOT NULL,
                direction  TEXT NOT NULL,   -- inbound | outbound
                from_id    TEXT,
                text       TEXT,
                reply      TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS vault (
                name       TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS telemetry_points (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                ts    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                name  TEXT NOT NULL,
                value REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS telemetry_logs (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                source  TEXT,
                level   TEXT,
                message TEXT
            );

            CREATE TABLE IF NOT EXISTS aiops_alerts (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                severity   TEXT NOT NULL DEFAULT 'info',
                status     TEXT NOT NULL DEFAULT 'open',
                message    TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS aiops_topology_nodes (
                name  TEXT PRIMARY KEY,
                layer TEXT
            );

            CREATE TABLE IF NOT EXISTS aiops_topology_edges (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                source  TEXT NOT NULL,   -- depends on target
                target  TEXT NOT NULL,
                UNIQUE(source, target)
            );

            CREATE TABLE IF NOT EXISTS aiops_incidents (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'open',
                description TEXT,
                symptom     TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS aiops_incident_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                kind        TEXT NOT NULL,
                data        TEXT,
                ts          TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS aiops_remediation (
                id           TEXT PRIMARY KEY,
                incident_id  TEXT NOT NULL,
                action       TEXT,
                service      TEXT,
                status       TEXT NOT NULL DEFAULT 'pending',
                verified     INTEGER DEFAULT 0,
                created_at   TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at   TEXT
            );

            CREATE TABLE IF NOT EXISTS aiops_chaos_runs (
                id         TEXT PRIMARY KEY,
                target     TEXT NOT NULL,
                fault_type TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'running',
                stopped    INTEGER DEFAULT 0,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                ended_at   TEXT
            );

            CREATE TABLE IF NOT EXISTS users (
                name        TEXT PRIMARY KEY,
                role        TEXT NOT NULL DEFAULT 'viewer',
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         TEXT NOT NULL DEFAULT (datetime('now')),
                actor      TEXT,
                action     TEXT NOT NULL,
                subject    TEXT,
                detail     TEXT,
                immutable  INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS economy_accounts (
                name       TEXT PRIMARY KEY,
                kind       TEXT NOT NULL DEFAULT 'user',
                balance    REAL NOT NULL DEFAULT 0,
                reputation REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS economy_gigs (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                reward     REAL NOT NULL,
                owner      TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'open',  -- open|claimed|completed|paid
                performer  TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS economy_ledger (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        TEXT NOT NULL DEFAULT (datetime('now')),
                src       TEXT,
                dst       TEXT,
                amount    REAL NOT NULL,
                ref       TEXT,
                note      TEXT
            );

            CREATE TABLE IF NOT EXISTS economy_keys (
                name        TEXT PRIMARY KEY,
                public_pem  TEXT NOT NULL,
                private_pem TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS economy_challenges (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                name   TEXT NOT NULL,
                nonce  TEXT NOT NULL,
                used   INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        _ensure_columns(
            con,
            "tasks",
            ["error"],
        )
        _ensure_columns(
            con,
            "messages",
            ["provider", "model", "input_tokens", "output_tokens"],
        )
        # FTS5 index for keyword search over memory chunks (used when available)
        try:
            con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(content)")
        except Exception:  # noqa: BLE001  (FTS5 not compiled into sqlite → keyword search falls back)
            pass
        _migrate(con)


# ------------------------------------------------------------------ schema versioning
# Controlled, one-time migrations keyed off `PRAGMA user_version`. Appending to
# this list (never editing an older entry) lets future schema changes migrate in
# place instead of depending on ad-hoc ALTER TABLE calls.
#
# Each entry: (version_number, "name", "sql_statement(s)").
# The version number MUST equal the list index (0-based) so user_version stays
# sequential and a fresh DB can replay them in order.
MIGRATIONS: list[tuple[int, str, str]] = [
    (0, "baseline", ""),
    # example future migration:
    # (1, "add_xyz_column", "ALTER TABLE messages ADD COLUMN xyz TEXT;"),
]


def _migrate(con: sqlite3.Connection) -> None:
    """Bring the schema version up to date, applying any missing migrations."""
    current = con.execute("PRAGMA user_version").fetchone()[0]
    target = len(MIGRATIONS) - 1
    for version, name, sql in MIGRATIONS:
        if version > current and sql:
            con.execute("BEGIN")
            try:
                con.executescript(sql)
                con.execute(f"PRAGMA user_version = {version}")
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
    # If a fresh DB was created at the baseline but user_version isn't set,
    # pin it to the latest known version so we don't replay/duplicate.
    if current == 0 and target >= 0:
        con.execute(f"PRAGMA user_version = {target}")
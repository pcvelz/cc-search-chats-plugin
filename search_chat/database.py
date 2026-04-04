"""SQLite FTS5 search index for Claude Code chat sessions."""

import sqlite3
import sys
import time
from pathlib import Path

from search_chat.parser import parse_session
from search_chat.types import CompactBoundary, ParsedMessage, SessionFile

DEFAULT_DB_PATH = Path.home() / '.claude' / 'search-index.db'
SCHEMA_VERSION = 2

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS session (
    session_id  TEXT PRIMARY KEY,
    project_dir TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    file_mtime  REAL NOT NULL,
    indexed_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS message (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid        TEXT,
    session_id  TEXT NOT NULL REFERENCES session(session_id) ON DELETE CASCADE,
    parent_uuid TEXT,
    epoch       INTEGER NOT NULL DEFAULT 0,
    timestamp   TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS compact_event (
    uuid               TEXT PRIMARY KEY,
    session_id         TEXT NOT NULL REFERENCES session(session_id) ON DELETE CASCADE,
    epoch              INTEGER NOT NULL,
    timestamp          TEXT NOT NULL,
    trigger_type       TEXT,
    token_count_before INTEGER
);

CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
    content,
    content='message',
    content_rowid='id',
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS message_fts_insert
AFTER INSERT ON message BEGIN
    INSERT INTO message_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS message_fts_delete
AFTER DELETE ON message BEGIN
    INSERT INTO message_fts(message_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS message_fts_update
AFTER UPDATE ON message BEGIN
    INSERT INTO message_fts(message_fts, rowid, content) VALUES ('delete', old.id, old.content);
    INSERT INTO message_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE INDEX IF NOT EXISTS idx_message_session ON message(session_id);
CREATE INDEX IF NOT EXISTS idx_message_session_epoch ON message(session_id, epoch);
"""


def open_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Open or create the search index database.

    Creates parent directories as needed. Verifies integrity of existing
    databases and recreates them if corrupt. Configures WAL mode and
    creates the schema on first use.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists() and db_path.stat().st_size > 0:
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.DatabaseError as exc:
            print(f"[search-index] corrupt database, rebuilding: {exc}", file=sys.stderr)
            conn.close()
            db_path.unlink()
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
    else:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")

    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create schema tables and update schema_version if needed."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()

    if row is None:
        # Fresh database — create everything
        conn.executescript(SCHEMA_SQL)
        conn.execute("INSERT OR REPLACE INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
        return

    current = conn.execute("SELECT version FROM schema_version").fetchone()
    if current is None or current["version"] != SCHEMA_VERSION:
        # Schema mismatch — recreate all tables
        conn.executescript(SCHEMA_SQL)
        conn.execute("INSERT OR REPLACE INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()


def close_db(conn: sqlite3.Connection) -> None:
    """Close the database connection."""
    conn.close()


def needs_reindex(conn: sqlite3.Connection, sf: SessionFile) -> bool:
    """Return True if the session is not indexed or the file has been modified."""
    row = conn.execute(
        "SELECT file_mtime FROM session WHERE session_id = ?",
        (sf.session_id,),
    ).fetchone()
    if row is None:
        return True
    return sf.mtime > row["file_mtime"]


def index_session(conn: sqlite3.Connection, sf: SessionFile) -> None:
    """Index a session file, replacing any existing data for that session."""
    # Remove existing data (cascade deletes messages and compact_events)
    conn.execute("DELETE FROM session WHERE session_id = ?", (sf.session_id,))

    conn.execute(
        "INSERT INTO session(session_id, project_dir, file_path, file_mtime, indexed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (sf.session_id, sf.project_dir, sf.file_path, sf.mtime, time.time()),
    )

    epoch = 0
    for record in parse_session(sf.file_path):
        if isinstance(record, CompactBoundary):
            epoch += 1
            conn.execute(
                "INSERT OR REPLACE INTO compact_event"
                "(uuid, session_id, epoch, timestamp, trigger_type, token_count_before) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.uuid,
                    sf.session_id,
                    epoch,
                    record.timestamp,
                    record.trigger_type,
                    record.token_count_before,
                ),
            )
        elif isinstance(record, ParsedMessage):
            conn.execute(
                "INSERT INTO message(uuid, session_id, parent_uuid, epoch, timestamp, role, content) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.uuid,
                    sf.session_id,
                    record.parent_uuid,
                    epoch,
                    record.timestamp,
                    record.role,
                    record.content,
                ),
            )

    conn.commit()


def jit_reindex(conn: sqlite3.Connection, session_files: list[SessionFile]) -> int:
    """Re-index only stale sessions. Returns the count of sessions reindexed."""
    count = 0
    for sf in session_files:
        if needs_reindex(conn, sf):
            index_session(conn, sf)
            count += 1
    return count


def fts_search(
    conn: sqlite3.Connection,
    query: str,
    project_dir: str | None = None,
    limit: int = 10,
) -> list[sqlite3.Row]:
    """Full-text search returning individual message hits.

    Returns rows with: session_id, epoch, timestamp, role, snippet, score.
    Returns an empty list on FTS query errors.
    """
    snippet_expr = "snippet(message_fts, 0, '«', '»', '…', 20)"

    if project_dir is not None:
        sql = f"""
            SELECT
                m.session_id,
                m.epoch,
                m.timestamp,
                m.role,
                {snippet_expr} AS snippet,
                fts.rank           AS score
            FROM message_fts fts
            JOIN message m ON m.id = fts.rowid
            JOIN session s ON s.session_id = m.session_id
            WHERE message_fts MATCH ?
              AND s.project_dir = ?
            ORDER BY fts.rank
            LIMIT ?
        """
        params = (query, project_dir, limit)
    else:
        sql = f"""
            SELECT
                m.session_id,
                m.epoch,
                m.timestamp,
                m.role,
                {snippet_expr} AS snippet,
                fts.rank           AS score
            FROM message_fts fts
            JOIN message m ON m.id = fts.rowid
            WHERE message_fts MATCH ?
            ORDER BY fts.rank
            LIMIT ?
        """
        params = (query, limit)

    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []


def search_sessions_aggregate(
    conn: sqlite3.Connection,
    query: str,
    project_dir: str | None = None,
    limit: int = 10,
) -> list[sqlite3.Row]:
    """Aggregate FTS5 results by session.

    Returns rows with: session_id, match_count, best_score, latest_timestamp, snippet.
    """
    snippet_expr = "snippet(message_fts, 0, '«', '»', '…', 20)"

    project_clause = "AND s.project_dir = ?" if project_dir is not None else ""
    project_join = "JOIN session s ON s.session_id = m.session_id" if project_dir is not None else ""

    sql = f"""
        WITH hits AS (
            SELECT
                m.session_id,
                m.timestamp,
                fts.rank AS score
            FROM message_fts fts
            JOIN message m ON m.id = fts.rowid
            {project_join}
            WHERE message_fts MATCH ?
            {project_clause}
        )
        SELECT
            session_id,
            COUNT(*)           AS match_count,
            MIN(score)         AS best_score,
            MAX(timestamp)     AS latest_timestamp,
            (SELECT {snippet_expr}
             FROM message_fts fts2
             JOIN message m2 ON m2.id = fts2.rowid
             WHERE message_fts MATCH ? AND m2.session_id = hits.session_id
             LIMIT 1)          AS snippet
        FROM hits
        GROUP BY session_id
        ORDER BY match_count DESC
        LIMIT ?
    """

    params: list = [query]
    if project_dir is not None:
        params.append(project_dir)
    params.extend([query, limit])

    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []


def get_session_messages(
    conn: sqlite3.Connection,
    session_id: str,
    epoch: int | None = None,
) -> list[sqlite3.Row]:
    """Retrieve messages for a session, optionally filtered by epoch."""
    if epoch is not None:
        sql = """
            SELECT id, uuid, session_id, parent_uuid, epoch, timestamp, role, content
            FROM message
            WHERE session_id = ? AND epoch = ?
            ORDER BY timestamp, id
        """
        params = (session_id, epoch)
    else:
        sql = """
            SELECT id, uuid, session_id, parent_uuid, epoch, timestamp, role, content
            FROM message
            WHERE session_id = ?
            ORDER BY timestamp, id
        """
        params = (session_id,)

    return conn.execute(sql, params).fetchall()


def get_session_epochs(conn: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
    """Return compact_event records for a session, ordered by epoch."""
    return conn.execute(
        "SELECT uuid, session_id, epoch, timestamp, trigger_type, token_count_before "
        "FROM compact_event "
        "WHERE session_id = ? "
        "ORDER BY epoch",
        (session_id,),
    ).fetchall()

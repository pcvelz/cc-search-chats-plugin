"""SQLite FTS5 search index for Claude Code chat sessions."""

import sqlite3
import sys
import time
from pathlib import Path

import json

from search_chat.parser import parse_line
from search_chat.types import CompactBoundary, ParsedMessage, SessionFile

DEFAULT_DB_PATH = Path.home() / '.claude' / 'search-index.db'
# v3: session.file_size / session.epoch enable append-only incremental
# indexing; session.missing_since gives deleted transcripts a grace period.
SCHEMA_VERSION = 3

# Sentinel for session.file_size: indexed by a pre-v3 indexer and the file has
# changed since, so the byte offset is unknown; the next change reindexes in full.
OFFSET_UNKNOWN = -1

# Claude Code deletes transcripts after ~30 days. A session whose transcript
# is gone stays searchable from the index for this long before it is pruned.
MISSING_GRACE_DAYS = 30
MISSING_GRACE_SECONDS = MISSING_GRACE_DAYS * 86400

# Columns added to `session` after v2, as (name, DDL) - the migration adds
# whichever are absent. Keep in sync with SCHEMA_SQL.
_SESSION_COLUMNS_ADDED = (
    ('file_size', 'INTEGER NOT NULL DEFAULT 0'),
    ('epoch', 'INTEGER NOT NULL DEFAULT 0'),
    ('missing_since', 'REAL'),
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS session (
    session_id    TEXT PRIMARY KEY,
    project_dir   TEXT NOT NULL,
    file_path     TEXT NOT NULL,
    file_mtime    REAL NOT NULL,
    indexed_at    REAL NOT NULL,
    file_size     INTEGER NOT NULL DEFAULT 0,
    epoch         INTEGER NOT NULL DEFAULT 0,
    missing_since REAL
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

    Creates parent directories as needed. Probes existing databases for
    unreadable header/schema corruption and recreates them if unreadable.
    Configures WAL mode and creates the schema on first use.

    The probe reads only the schema page. A full `PRAGMA integrity_check`
    walks every page of the index (810 MB, 2-9 s) and was running on EVERY
    invocation, dwarfing the actual search (~0.15 s). Page-level corruption
    that the probe cannot see surfaces as a DatabaseError on the query that
    hits it, which is the right time to pay for a rebuild, not up front.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists() and db_path.stat().st_size > 0:
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
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

    if not _ensure_schema(conn):
        # Unknown schema version (not one the adapter below can migrate):
        # rebuild. CREATE IF NOT EXISTS cannot reshape existing tables, and
        # unlinking also reclaims the file's free pages.
        print(f"[search-index] unknown index schema, rebuilding as v{SCHEMA_VERSION}", file=sys.stderr)
        conn.close()
        for suffix in ('', '-wal', '-shm'):
            Path(str(db_path) + suffix).unlink(missing_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> bool:
    """Create the schema on a fresh database, or migrate a known older one in
    place. Returns False when the version is unknown (caller rebuilds)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()

    if row is None:
        conn.executescript(SCHEMA_SQL)
        conn.execute("INSERT OR REPLACE INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
        return True

    current = conn.execute("SELECT version FROM schema_version").fetchone()
    version = current["version"] if current is not None else None
    if version == SCHEMA_VERSION:
        _add_missing_session_columns(conn)
        return True
    if version == 2:
        _migrate_v2_to_v3(conn)
        return True
    return False


def _add_missing_session_columns(conn: sqlite3.Connection) -> list[str]:
    """ALTER TABLE session ADD COLUMN for every v3 column not yet present.
    Existing rows, messages and FTS content are untouched. Returns the names
    added (empty when the table is already complete)."""
    present = {r["name"] for r in conn.execute("PRAGMA table_info(session)")}
    added = []
    for name, ddl in _SESSION_COLUMNS_ADDED:
        if name not in present:
            conn.execute(f"ALTER TABLE session ADD COLUMN {name} {ddl}")
            added.append(name)
    if added:
        conn.commit()
    return added


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    # DEPRECATED v2 adapter - remove on or after 2026-10-12 (added 2026-09-12
    # + 30 days). After removal a v2 index falls through to the rebuild path.
    """Migrate a v2 index in place so no searchable history is lost on upgrade.

    v2 rows carry no byte offset. For a session whose transcript is unchanged
    since v2 indexed it (mtime not newer), every complete line is already in
    the index, so the offset is the file's current size and the epoch is the
    number of compact events recorded - the incremental indexer can resume
    exactly there without re-parsing. A transcript that changed since (or is
    gone) gets OFFSET_UNKNOWN, which makes its next change a full reindex,
    so nothing is ever appended twice.
    """
    print(f"[search-index] migrating index v2 -> v{SCHEMA_VERSION} in place", file=sys.stderr)
    added = _add_missing_session_columns(conn)
    if 'file_size' in added:
        rows = conn.execute("SELECT session_id, file_path, file_mtime FROM session").fetchall()
        for row in rows:
            file_size = OFFSET_UNKNOWN
            try:
                st = Path(row["file_path"]).stat()
                if st.st_mtime <= row["file_mtime"]:
                    file_size = st.st_size
            except OSError:
                pass
            epoch = conn.execute(
                "SELECT COUNT(*) FROM compact_event WHERE session_id = ?", (row["session_id"],),
            ).fetchone()[0]
            conn.execute(
                "UPDATE session SET file_size = ?, epoch = ? WHERE session_id = ?",
                (file_size, epoch, row["session_id"]),
            )
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
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


def _insert_record(conn: sqlite3.Connection, session_id: str, record, epoch: int) -> int:
    """Insert one parsed record; returns the (possibly advanced) epoch."""
    if isinstance(record, CompactBoundary):
        epoch += 1
        conn.execute(
            "INSERT OR REPLACE INTO compact_event"
            "(uuid, session_id, epoch, timestamp, trigger_type, token_count_before) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (record.uuid, session_id, epoch, record.timestamp,
             record.trigger_type, record.token_count_before),
        )
    elif isinstance(record, ParsedMessage):
        conn.execute(
            "INSERT INTO message(uuid, session_id, parent_uuid, epoch, timestamp, role, content) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (record.uuid, session_id, record.parent_uuid, epoch,
             record.timestamp, record.role, record.content),
        )
    return epoch


def _index_from(conn: sqlite3.Connection, sf: SessionFile, offset: int, epoch: int) -> tuple[int, int]:
    """Index the transcript from byte `offset` onward. Returns (new_offset, epoch).

    Reads in binary so the offset is exact. Only complete lines advance the
    offset: a trailing line still being written by the live session (no
    newline yet, or unparseable JSON) is left for the next run, so it is
    neither lost nor indexed twice. Transcripts are append-only, which is
    what makes resuming from an offset sound.
    """
    try:
        with open(sf.file_path, 'rb') as fh:
            fh.seek(offset)
            for raw in fh:
                line = raw.decode('utf-8', errors='replace').strip()
                if not raw.endswith(b'\n'):
                    try:
                        json.loads(line)
                    except ValueError:
                        break
                offset += len(raw)
                if line:
                    epoch = _insert_record(conn, sf.session_id, parse_line(line), epoch)
    except OSError:
        pass
    return offset, epoch


def _record_progress(conn: sqlite3.Connection, sf: SessionFile, offset: int, epoch: int) -> None:
    conn.execute(
        "UPDATE session SET file_mtime = ?, indexed_at = ?, file_size = ?, epoch = ? "
        "WHERE session_id = ?",
        (sf.mtime, time.time(), offset, epoch, sf.session_id),
    )


def index_session(conn: sqlite3.Connection, sf: SessionFile) -> None:
    """Index a session file from scratch, replacing any existing data for it."""
    # Remove existing data (cascade deletes messages and compact_events)
    conn.execute("DELETE FROM session WHERE session_id = ?", (sf.session_id,))
    conn.execute(
        "INSERT INTO session(session_id, project_dir, file_path, file_mtime, indexed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (sf.session_id, sf.project_dir, sf.file_path, sf.mtime, time.time()),
    )
    offset, epoch = _index_from(conn, sf, 0, 0)
    _record_progress(conn, sf, offset, epoch)
    conn.commit()


def append_session(conn: sqlite3.Connection, sf: SessionFile) -> None:
    """Index only the bytes appended since the session was last indexed.

    A live session changes on every turn; re-parsing the whole transcript on
    every search cost 0.3-2.8s per call with several sessions open. Falls back
    to a full index when the file shrank (rewritten, not appended) or was
    never indexed.
    """
    row = conn.execute(
        "SELECT file_size, epoch FROM session WHERE session_id = ?", (sf.session_id,),
    ).fetchone()
    if row is None or row["file_size"] == OFFSET_UNKNOWN or sf.size < row["file_size"]:
        index_session(conn, sf)
        return
    offset, epoch = _index_from(conn, sf, row["file_size"], row["epoch"])
    _record_progress(conn, sf, offset, epoch)
    conn.commit()


def prune_missing(
    conn: sqlite3.Connection,
    session_files: list[SessionFile],
    project_dirs: set[str] | None = None,
    now: float | None = None,
) -> int:
    """Track indexed sessions whose transcript is gone; prune after the grace period.

    `session_files` is the complete on-disk listing for the scope; scope is
    `project_dirs` (None = every project). A session first seen missing gets
    `missing_since` stamped and stays searchable (and extractable from the
    index); it is deleted only once missing for longer than
    MISSING_GRACE_SECONDS, so Claude Code's ~30-day transcript cleanup does
    not silently erase searchable history. A transcript that reappears
    clears the stamp. Agent transcripts are only judged when the listing
    included them, since they are hidden from listings by default. Returns
    the number of sessions pruned.
    """
    now = time.time() if now is None else now
    listed = {sf.session_id for sf in session_files}
    agents_listed = any(sid.startswith('agent-') for sid in listed)
    pruned = 0
    changed = False
    rows = conn.execute("SELECT session_id, project_dir, missing_since FROM session").fetchall()
    for row in rows:
        sid = row["session_id"]
        if project_dirs is not None and row["project_dir"] not in project_dirs:
            continue
        if sid in listed:
            if row["missing_since"] is not None:
                conn.execute("UPDATE session SET missing_since = NULL WHERE session_id = ?", (sid,))
                changed = True
            continue
        if sid.startswith('agent-') and not agents_listed:
            continue
        if row["missing_since"] is None:
            conn.execute("UPDATE session SET missing_since = ? WHERE session_id = ?", (now, sid))
            changed = True
        elif now - row["missing_since"] > MISSING_GRACE_SECONDS:
            conn.execute("DELETE FROM session WHERE session_id = ?", (sid,))
            pruned += 1
            changed = True
    if changed:
        conn.commit()
    return pruned


def get_missing_since(conn: sqlite3.Connection, session_ids: list[str]) -> dict[str, float]:
    """Map session_id -> missing_since for those of `session_ids` whose
    transcript is gone (in their grace period). Present sessions are absent."""
    if not session_ids:
        return {}
    placeholders = ','.join('?' * len(session_ids))
    rows = conn.execute(
        f"SELECT session_id, missing_since FROM session "
        f"WHERE session_id IN ({placeholders}) AND missing_since IS NOT NULL",
        session_ids,
    ).fetchall()
    return {r["session_id"]: r["missing_since"] for r in rows}


def find_indexed_session(conn: sqlite3.Connection, session_id: str) -> str | None:
    """Resolve a full or prefix session id against the index alone. Used when
    the transcript is no longer on disk but the session is still in its
    grace period. Returns the full id, or None."""
    row = conn.execute(
        "SELECT session_id FROM session WHERE session_id = ? OR session_id LIKE ? "
        "ORDER BY session_id LIMIT 1",
        (session_id, session_id + '%'),
    ).fetchone()
    return row["session_id"] if row else None


REINDEX_NOTICE_THRESHOLD = 25


def jit_reindex(conn: sqlite3.Connection, session_files: list[SessionFile]) -> int:
    """Bring stale sessions up to date. Returns the count of sessions touched.

    Already-indexed sessions are extended from their recorded byte offset;
    new ones are indexed in full. A large backlog (first --all-projects run
    over hundreds of sessions takes ~15s) is announced on stderr so the pause
    reads as work, not a hang.
    """
    stale = [sf for sf in session_files if needs_reindex(conn, sf)]
    if len(stale) >= REINDEX_NOTICE_THRESHOLD:
        total_mb = sum(sf.size for sf in stale) / 1e6
        print(f'[search-index] indexing {len(stale)} sessions ({total_mb:.0f} MB), one-time...',
              file=sys.stderr)
    for sf in stale:
        append_session(conn, sf)
    return len(stale)


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
) -> list[dict]:
    """Aggregate FTS5 results by session.

    Returns dicts with: session_id, match_count, best_score, latest_timestamp, snippet.

    One MATCH pass ranks every hit and tags each session's best-ranked row
    with a window function; snippets are then point lookups by rowid for only
    the `limit` sessions returned. The previous correlated snippet subquery
    re-ran the MATCH for every session that had any hit (not just the
    returned ones), which was 97% of the query time for common terms
    (1.26s vs 0.04s for "deploy"* over 1.1M messages).
    """
    project_clause = "AND s.project_dir = ?" if project_dir is not None else ""
    project_join = "JOIN session s ON s.session_id = m.session_id" if project_dir is not None else ""

    sql = f"""
        WITH hits AS (
            SELECT
                m.session_id,
                m.timestamp,
                fts.rank  AS score,
                fts.rowid AS rowid,
                ROW_NUMBER() OVER (PARTITION BY m.session_id ORDER BY fts.rank) AS rn
            FROM message_fts fts
            JOIN message m ON m.id = fts.rowid
            {project_join}
            WHERE message_fts MATCH ?
            {project_clause}
        )
        SELECT
            session_id,
            COUNT(*)                            AS match_count,
            MIN(score)                          AS best_score,
            MAX(timestamp)                      AS latest_timestamp,
            MAX(CASE WHEN rn = 1 THEN rowid END) AS best_rowid
        FROM hits
        GROUP BY session_id
        ORDER BY match_count DESC
        LIMIT ?
    """

    params: list = [query]
    if project_dir is not None:
        params.append(project_dir)
    params.append(limit)

    snippet_sql = (
        "SELECT snippet(message_fts, 0, '«', '»', '…', 20) "
        "FROM message_fts WHERE rowid = ? AND message_fts MATCH ?"
    )
    try:
        rows = conn.execute(sql, params).fetchall()
        results = []
        for row in rows:
            snippet_row = conn.execute(snippet_sql, (row["best_rowid"], query)).fetchone()
            results.append({
                "session_id": row["session_id"],
                "match_count": row["match_count"],
                "best_score": row["best_score"],
                "latest_timestamp": row["latest_timestamp"],
                "snippet": snippet_row[0] if snippet_row else "",
            })
        return results
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

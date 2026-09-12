-- Frozen v2 index schema (SCHEMA_VERSION = 2), captured verbatim from the
-- last v2 release of search_chat/database.py. Used only to build synthetic v2
-- databases for the v2 -> v3 migration tests, so they keep testing the real
-- old shape after HEAD moves on and in checkouts without git (npm, tarball).
-- Remove together with the v2 adapter (_migrate_v2_to_v3) on or after
-- 2026-10-12.

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

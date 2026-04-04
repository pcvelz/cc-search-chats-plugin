"""Tests for SQLite database layer."""
import sqlite3
from pathlib import Path

from search_chat.database import (
    close_db,
    fts_search,
    get_session_epochs,
    get_session_messages,
    index_session,
    jit_reindex,
    needs_reindex,
    open_db,
    search_sessions_aggregate,
)
from search_chat.types import SessionFile


def _make_session_file(fixture_path: str, session_id: str, project_dir: str) -> SessionFile:
    p = Path(fixture_path)
    stat = p.stat()
    return SessionFile(
        session_id=session_id, file_path=fixture_path,
        project_dir=project_dir, mtime=stat.st_mtime, size=stat.st_size,
    )


class TestOpenDb:
    def test_creates_schema(self, tmp_db):
        conn = open_db(tmp_db)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t['name'] for t in tables]
        assert 'session' in table_names
        assert 'message' in table_names
        assert 'compact_event' in table_names
        close_db(conn)

    def test_wal_mode(self, tmp_db):
        conn = open_db(tmp_db)
        mode = conn.execute('PRAGMA journal_mode').fetchone()[0]
        assert mode == 'wal'
        close_db(conn)

    def test_idempotent_open(self, tmp_db):
        conn1 = open_db(tmp_db)
        close_db(conn1)
        conn2 = open_db(tmp_db)
        tables = conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session'"
        ).fetchone()
        assert tables is not None
        close_db(conn2)

    def test_corrupt_db_rebuilds(self, tmp_db):
        tmp_db.parent.mkdir(parents=True, exist_ok=True)
        tmp_db.write_bytes(b'THIS IS NOT A SQLITE DATABASE')
        conn = open_db(tmp_db)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session'"
        ).fetchone()
        assert tables is not None
        close_db(conn)


class TestIndexSession:
    def test_index_simple_session(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        sf = _make_session_file(sample_session_path, 'sess-aaa', '-tmp-test')
        index_session(conn, sf)
        messages = get_session_messages(conn, 'sess-aaa')
        assert len(messages) == 4
        assert all(m['epoch'] == 0 for m in messages)
        close_db(conn)

    def test_index_compressed_session_epochs(self, tmp_db, compressed_session_path):
        conn = open_db(tmp_db)
        sf = _make_session_file(compressed_session_path, 'sess-bbb', '-tmp-test')
        index_session(conn, sf)
        messages = get_session_messages(conn, 'sess-bbb')
        assert len(messages) == 4
        epoch0 = [m for m in messages if m['epoch'] == 0]
        epoch1 = [m for m in messages if m['epoch'] == 1]
        assert len(epoch0) == 2
        assert len(epoch1) == 2
        epochs = get_session_epochs(conn, 'sess-bbb')
        assert len(epochs) == 1
        assert epochs[0]['trigger_type'] == 'auto'
        assert epochs[0]['token_count_before'] == 48000
        close_db(conn)

    def test_reindex_replaces_data(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        sf = _make_session_file(sample_session_path, 'sess-aaa', '-tmp-test')
        index_session(conn, sf)
        index_session(conn, sf)
        messages = get_session_messages(conn, 'sess-aaa')
        assert len(messages) == 4
        close_db(conn)

    def test_cascade_delete(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        sf = _make_session_file(sample_session_path, 'sess-aaa', '-tmp-test')
        index_session(conn, sf)
        conn.execute('DELETE FROM session WHERE session_id = ?', ('sess-aaa',))
        conn.commit()
        messages = get_session_messages(conn, 'sess-aaa')
        assert len(messages) == 0
        close_db(conn)


class TestNeedsReindex:
    def test_new_session_needs_reindex(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        sf = _make_session_file(sample_session_path, 'sess-aaa', '-tmp-test')
        assert needs_reindex(conn, sf) is True
        close_db(conn)

    def test_indexed_session_not_stale(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        sf = _make_session_file(sample_session_path, 'sess-aaa', '-tmp-test')
        index_session(conn, sf)
        assert needs_reindex(conn, sf) is False
        close_db(conn)


class TestJitReindex:
    def test_indexes_new_sessions(self, tmp_db, sample_session_path, compressed_session_path):
        conn = open_db(tmp_db)
        files = [
            _make_session_file(sample_session_path, 'sess-aaa', '-tmp-test'),
            _make_session_file(compressed_session_path, 'sess-bbb', '-tmp-test'),
        ]
        count = jit_reindex(conn, files)
        assert count == 2
        close_db(conn)

    def test_skips_already_indexed(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        sf = _make_session_file(sample_session_path, 'sess-aaa', '-tmp-test')
        index_session(conn, sf)
        count = jit_reindex(conn, [sf])
        assert count == 0
        close_db(conn)


class TestFtsSearch:
    def test_keyword_search(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        sf = _make_session_file(sample_session_path, 'sess-aaa', '-tmp-test')
        index_session(conn, sf)
        results = fts_search(conn, 'redis')
        assert len(results) >= 1
        close_db(conn)

    def test_no_results(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        sf = _make_session_file(sample_session_path, 'sess-aaa', '-tmp-test')
        index_session(conn, sf)
        results = fts_search(conn, 'nonexistent_term_xyz')
        assert len(results) == 0
        close_db(conn)

    def test_project_filter(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        sf = _make_session_file(sample_session_path, 'sess-aaa', '-tmp-test')
        index_session(conn, sf)
        results = fts_search(conn, 'redis', project_dir='-tmp-test')
        assert len(results) >= 1
        results = fts_search(conn, 'redis', project_dir='-other-project')
        assert len(results) == 0
        close_db(conn)


class TestSearchSessionsAggregate:
    def test_aggregate_by_session(self, tmp_db, sample_session_path, compressed_session_path):
        conn = open_db(tmp_db)
        index_session(conn, _make_session_file(sample_session_path, 'sess-aaa', '-tmp-test'))
        index_session(conn, _make_session_file(compressed_session_path, 'sess-bbb', '-tmp-test'))
        results = search_sessions_aggregate(conn, 'migration')
        assert len(results) >= 1
        assert results[0]['match_count'] >= 1
        close_db(conn)

"""Tests for SQLite database layer."""
import sqlite3
from pathlib import Path

import json
import os
import shutil

from search_chat.database import (
    MISSING_GRACE_SECONDS,
    OFFSET_UNKNOWN,
    SCHEMA_VERSION,
    append_session,
    close_db,
    find_indexed_session,
    fts_search,
    get_missing_since,
    get_session_epochs,
    get_session_messages,
    index_session,
    jit_reindex,
    needs_reindex,
    open_db,
    prune_missing,
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


def _append_line(path: Path, payload: dict, newline: bool = True) -> None:
    with open(path, 'a') as fh:
        fh.write(json.dumps(payload) + ('\n' if newline else ''))
    # Force a strictly newer mtime than the indexed one.
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + 1))


def _user_line(uuid: str, text: str) -> dict:
    return {"type": "user", "uuid": uuid, "timestamp": "2026-01-01T00:00:00Z",
            "message": {"role": "user", "content": text}}


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

    def test_unknown_schema_version_rebuilds(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        index_session(conn, _make_session_file(sample_session_path, 'sess-aaa', '-tmp-test'))
        conn.execute('UPDATE schema_version SET version = 99')
        conn.commit()
        close_db(conn)
        conn = open_db(tmp_db)
        assert conn.execute('SELECT version FROM schema_version').fetchone()[0] == SCHEMA_VERSION
        assert conn.execute('SELECT COUNT(*) FROM session').fetchone()[0] == 0
        close_db(conn)

    def test_v3_missing_column_added_in_place(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        index_session(conn, _make_session_file(sample_session_path, 'sess-aaa', '-tmp-test'))
        conn.execute('ALTER TABLE session DROP COLUMN missing_since')
        conn.commit()
        close_db(conn)
        conn = open_db(tmp_db)
        cols = {r[1] for r in conn.execute('PRAGMA table_info(session)')}
        assert 'missing_since' in cols
        assert len(get_session_messages(conn, 'sess-aaa')) == 4
        close_db(conn)


_SCHEMA_V2_SQL = Path(__file__).parent / 'fixtures' / 'schema_v2.sql'


def _index_as_v2(db_path: Path, sf: SessionFile) -> None:
    """Build a v2 index for `sf` the way the v2 plugin did: frozen v2 schema
    from tests/fixtures/schema_v2.sql (no git, no subprocess), a session row
    without byte offset, and messages/compact events with a counted epoch."""
    from search_chat.parser import parse_session
    from search_chat.types import CompactBoundary, ParsedMessage
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA_V2_SQL.read_text())
    conn.execute('INSERT OR REPLACE INTO schema_version(version) VALUES (2)')
    conn.execute(
        'INSERT INTO session(session_id, project_dir, file_path, file_mtime, indexed_at) '
        'VALUES (?, ?, ?, ?, ?)',
        (sf.session_id, sf.project_dir, sf.file_path, sf.mtime, sf.mtime),
    )
    epoch = 0
    for record in parse_session(sf.file_path):
        if isinstance(record, CompactBoundary):
            epoch += 1
            conn.execute(
                'INSERT INTO compact_event(uuid, session_id, epoch, timestamp, trigger_type, token_count_before) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (record.uuid, sf.session_id, epoch, record.timestamp,
                 record.trigger_type, record.token_count_before),
            )
        elif isinstance(record, ParsedMessage):
            conn.execute(
                'INSERT INTO message(uuid, session_id, parent_uuid, epoch, timestamp, role, content) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)',
                (record.uuid, sf.session_id, record.parent_uuid, epoch,
                 record.timestamp, record.role, record.content),
            )
    conn.commit()
    cols = {r[1] for r in conn.execute('PRAGMA table_info(session)')}
    assert 'file_size' not in cols and 'missing_since' not in cols
    conn.close()


class TestMigrateV2ToV3:
    def _v2_index(self, tmp_db, tmp_path, fixture_path):
        p = tmp_path / 'live.jsonl'
        shutil.copy(fixture_path, p)
        sf = _make_session_file(str(p), 'live', '-tmp-test')
        _index_as_v2(tmp_db, sf)
        return p, sf

    def test_rows_kept_and_no_duplicates_on_next_increment(self, tmp_db, tmp_path, sample_session_path):
        p, sf = self._v2_index(tmp_db, tmp_path, sample_session_path)
        conn = open_db(tmp_db)
        assert conn.execute('SELECT version FROM schema_version').fetchone()[0] == SCHEMA_VERSION
        assert len(get_session_messages(conn, 'live')) == 4
        assert fts_search(conn, 'redis')
        row = conn.execute('SELECT file_size, epoch FROM session WHERE session_id = ?', ('live',)).fetchone()
        assert row['file_size'] == p.stat().st_size and row['epoch'] == 0
        # Unchanged since v2 indexed it: nothing to do.
        assert jit_reindex(conn, [sf]) == 0
        # Appended turn: extended from the migrated offset, not re-parsed.
        _append_line(p, _user_line('u-new', 'post-migration turn'))
        assert jit_reindex(conn, [_make_session_file(str(p), 'live', '-tmp-test')]) == 1
        contents = [m['content'] for m in get_session_messages(conn, 'live')]
        assert len(contents) == 5 and contents.count('post-migration turn') == 1
        close_db(conn)

    def test_changed_since_v2_gets_full_reindex_once(self, tmp_db, tmp_path, sample_session_path):
        p, _ = self._v2_index(tmp_db, tmp_path, sample_session_path)
        # Transcript grew after v2 indexed it, before the upgrade ran.
        _append_line(p, _user_line('u-new', 'grew before upgrade'))
        conn = open_db(tmp_db)
        row = conn.execute('SELECT file_size FROM session WHERE session_id = ?', ('live',)).fetchone()
        assert row['file_size'] == OFFSET_UNKNOWN
        assert jit_reindex(conn, [_make_session_file(str(p), 'live', '-tmp-test')]) == 1
        contents = [m['content'] for m in get_session_messages(conn, 'live')]
        assert len(contents) == 5 and contents.count('grew before upgrade') == 1
        close_db(conn)

    def test_epoch_carried_from_compact_events(self, tmp_db, tmp_path, compressed_session_path):
        p, _ = self._v2_index(tmp_db, tmp_path, compressed_session_path)
        conn = open_db(tmp_db)
        row = conn.execute('SELECT epoch FROM session WHERE session_id = ?', ('live',)).fetchone()
        assert row['epoch'] == 1
        _append_line(p, _user_line('u-new', 'after compaction'))
        jit_reindex(conn, [_make_session_file(str(p), 'live', '-tmp-test')])
        msgs = {m['content']: m['epoch'] for m in get_session_messages(conn, 'live')}
        assert msgs['after compaction'] == 1
        close_db(conn)

    def test_missing_transcript_gets_unknown_offset(self, tmp_db, tmp_path, sample_session_path):
        p, _ = self._v2_index(tmp_db, tmp_path, sample_session_path)
        p.unlink()
        conn = open_db(tmp_db)
        row = conn.execute('SELECT file_size, missing_since FROM session WHERE session_id = ?', ('live',)).fetchone()
        assert row['file_size'] == OFFSET_UNKNOWN and row['missing_since'] is None
        assert len(get_session_messages(conn, 'live')) == 4
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


class TestAppendSession:
    def _live(self, tmp_path, fixture_path, name='live.jsonl'):
        p = tmp_path / name
        shutil.copy(fixture_path, p)
        return p

    def test_append_indexes_only_new_lines(self, tmp_db, tmp_path, sample_session_path):
        conn = open_db(tmp_db)
        p = self._live(tmp_path, sample_session_path)
        index_session(conn, _make_session_file(str(p), 'live', '-tmp-test'))
        before = [m['id'] for m in get_session_messages(conn, 'live')]
        _append_line(p, _user_line('u-new', 'appended turn about kubernetesq'))
        assert jit_reindex(conn, [_make_session_file(str(p), 'live', '-tmp-test')]) == 1
        after = get_session_messages(conn, 'live')
        assert len(after) == len(before) + 1
        # Existing rows were extended, not deleted and re-inserted.
        assert set(before) <= {m['id'] for m in after}
        assert 'appended turn about kubernetesq' in {m['content'] for m in after}
        assert fts_search(conn, 'kubernetesq')
        close_db(conn)

    def test_partial_trailing_line_deferred_then_indexed_once(self, tmp_db, tmp_path, sample_session_path):
        conn = open_db(tmp_db)
        p = self._live(tmp_path, sample_session_path)
        index_session(conn, _make_session_file(str(p), 'live', '-tmp-test'))
        n0 = len(get_session_messages(conn, 'live'))
        # Writer mid-line: a truncated JSON object with no newline.
        with open(p, 'a') as fh:
            fh.write('{"type": "user", "uuid": "u-half", "message": {"role": "user", "content": "hal')
        st = p.stat(); os.utime(p, (st.st_atime, st.st_mtime + 1))
        append_session(conn, _make_session_file(str(p), 'live', '-tmp-test'))
        assert len(get_session_messages(conn, 'live')) == n0
        with open(p, 'a') as fh:
            fh.write('f done"}}\n')
        st = p.stat(); os.utime(p, (st.st_atime, st.st_mtime + 2))
        append_session(conn, _make_session_file(str(p), 'live', '-tmp-test'))
        msgs = get_session_messages(conn, 'live')
        assert len(msgs) == n0 + 1
        assert [m['content'] for m in msgs].count('half done') == 1
        close_db(conn)

    def test_epoch_continues_across_appends(self, tmp_db, tmp_path, compressed_session_path):
        conn = open_db(tmp_db)
        p = self._live(tmp_path, compressed_session_path)
        index_session(conn, _make_session_file(str(p), 'live', '-tmp-test'))
        _append_line(p, _user_line('u-new', 'after the compaction'))
        append_session(conn, _make_session_file(str(p), 'live', '-tmp-test'))
        msgs = get_session_messages(conn, 'live')
        assert msgs[-1]['epoch'] == 1
        assert len(get_session_epochs(conn, 'live')) == 1
        close_db(conn)

    def test_shrunk_file_reindexes_fully(self, tmp_db, tmp_path, sample_session_path):
        conn = open_db(tmp_db)
        p = self._live(tmp_path, sample_session_path)
        index_session(conn, _make_session_file(str(p), 'live', '-tmp-test'))
        p.write_text(json.dumps(_user_line('u-only', 'rewritten')) + '\n')
        st = p.stat(); os.utime(p, (st.st_atime, st.st_mtime + 1))
        append_session(conn, _make_session_file(str(p), 'live', '-tmp-test'))
        msgs = get_session_messages(conn, 'live')
        assert [m['content'] for m in msgs] == ['rewritten']
        close_db(conn)


class TestPruneMissing:
    T0 = 1_800_000_000.0

    def _indexed(self, conn, fixture, *ids, project='-tmp-test'):
        sfs = [_make_session_file(fixture, sid, project) for sid in ids]
        for sf in sfs:
            index_session(conn, sf)
        return sfs

    def _ids(self, conn):
        return {r[0] for r in conn.execute('SELECT session_id FROM session')}

    def test_missing_within_grace_is_marked_and_kept(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        keep, gone = self._indexed(conn, sample_session_path, 'keep', 'gone')
        assert prune_missing(conn, [keep], {'-tmp-test'}, now=self.T0) == 0
        assert self._ids(conn) == {'keep', 'gone'}
        assert get_missing_since(conn, ['keep', 'gone']) == {'gone': self.T0}
        assert len(get_session_messages(conn, 'gone')) == 4
        assert find_indexed_session(conn, 'go') == 'gone'
        # Still within grace on a later run: kept, first-seen stamp unchanged.
        later = self.T0 + MISSING_GRACE_SECONDS - 1
        assert prune_missing(conn, [keep], {'-tmp-test'}, now=later) == 0
        assert get_missing_since(conn, ['gone']) == {'gone': self.T0}
        close_db(conn)

    def test_missing_past_grace_is_pruned(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        keep, gone = self._indexed(conn, sample_session_path, 'keep', 'gone')
        prune_missing(conn, [keep], {'-tmp-test'}, now=self.T0)
        expired = self.T0 + MISSING_GRACE_SECONDS + 1
        assert prune_missing(conn, [keep], {'-tmp-test'}, now=expired) == 1
        assert self._ids(conn) == {'keep'}
        assert get_session_messages(conn, 'gone') == []
        close_db(conn)

    def test_reappearing_transcript_clears_marker(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        keep, back = self._indexed(conn, sample_session_path, 'keep', 'back')
        prune_missing(conn, [keep], {'-tmp-test'}, now=self.T0)
        assert get_missing_since(conn, ['back']) == {'back': self.T0}
        prune_missing(conn, [keep, back], {'-tmp-test'}, now=self.T0 + 10)
        assert get_missing_since(conn, ['back']) == {}
        # Missing again much later: the clock restarts, so it is not pruned.
        again = self.T0 + MISSING_GRACE_SECONDS + 100
        assert prune_missing(conn, [keep], {'-tmp-test'}, now=again) == 0
        assert get_missing_since(conn, ['back']) == {'back': again}
        close_db(conn)

    def test_scope_limits_marking(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        (keep,) = self._indexed(conn, sample_session_path, 'keep')
        self._indexed(conn, sample_session_path, 'other', project='-tmp-other')
        prune_missing(conn, [keep], {'-tmp-test'}, now=self.T0)
        assert get_missing_since(conn, ['other']) == {}
        prune_missing(conn, [keep], None, now=self.T0)
        assert get_missing_since(conn, ['other']) == {'other': self.T0}
        close_db(conn)

    def test_agent_sessions_judged_only_when_agents_listed(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        main, _agent = self._indexed(conn, sample_session_path, 'main', 'agent-1')
        prune_missing(conn, [main], {'-tmp-test'}, now=self.T0)
        assert get_missing_since(conn, ['agent-1']) == {}
        listed_agent = _make_session_file(sample_session_path, 'agent-2', '-tmp-test')
        prune_missing(conn, [main, listed_agent], {'-tmp-test'}, now=self.T0)
        assert get_missing_since(conn, ['agent-1']) == {'agent-1': self.T0}
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

    def test_snippet_per_returned_session(self, tmp_db, sample_session_path, compressed_session_path):
        conn = open_db(tmp_db)
        index_session(conn, _make_session_file(sample_session_path, 'sess-aaa', '-tmp-test'))
        index_session(conn, _make_session_file(compressed_session_path, 'sess-bbb', '-tmp-test'))
        results = search_sessions_aggregate(conn, 'the', limit=1)
        assert len(results) == 1
        r = results[0]
        assert set(r) == {'session_id', 'match_count', 'best_score', 'latest_timestamp', 'snippet'}
        assert '«the»' in r['snippet'].lower()
        assert r['latest_timestamp']
        close_db(conn)

    def test_syntax_error_returns_empty(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        index_session(conn, _make_session_file(sample_session_path, 'sess-aaa', '-tmp-test'))
        assert search_sessions_aggregate(conn, 'redis-cache') == []
        close_db(conn)

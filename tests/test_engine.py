"""Tests for adaptive search engine."""
from pathlib import Path

from search_chat.database import close_db, index_session, open_db
from search_chat.engine import is_regex_query, normalize_query, search
from search_chat.types import SessionFile


def _make_sf(fixture_path: str, session_id: str) -> SessionFile:
    p = Path(fixture_path)
    stat = p.stat()
    return SessionFile(session_id=session_id, file_path=fixture_path,
                       project_dir='-tmp-test', mtime=stat.st_mtime, size=stat.st_size)


class TestQueryDetection:
    def test_simple_keyword(self):
        assert is_regex_query('redis') is False

    def test_multi_word(self):
        assert is_regex_query('deploy staging') is False

    def test_bre_or(self):
        assert is_regex_query(r'redis\|cache') is True

    def test_regex_dot_star(self):
        assert is_regex_query('deploy.*staging') is True

    def test_regex_bracket(self):
        assert is_regex_query('[Rr]edis') is True

    def test_quoted_phrase(self):
        assert is_regex_query('"exact phrase"') is False


class TestNormalizeQuery:
    def test_bre_to_ere(self):
        assert normalize_query(r'redis\|cache') == 'redis|cache'

    def test_passthrough(self):
        assert normalize_query('simple query') == 'simple query'


class TestSearch:
    def test_keyword_search_returns_results(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        index_session(conn, _make_sf(sample_session_path, 'sess-aaa'))
        results = search(conn, 'redis', project_dir='-tmp-test')
        assert len(results) >= 1
        assert results[0]['session_id'] == 'sess-aaa'
        assert results[0]['match_count'] >= 1
        close_db(conn)

    def test_regex_fallback(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        index_session(conn, _make_sf(sample_session_path, 'sess-aaa'))
        results = search(conn, r'redis\|staging', project_dir='-tmp-test')
        assert len(results) >= 1
        close_db(conn)

    def test_no_results(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        index_session(conn, _make_sf(sample_session_path, 'sess-aaa'))
        results = search(conn, 'completely_nonexistent_xyz')
        assert len(results) == 0
        close_db(conn)

    def test_exclude_session(self, tmp_db, sample_session_path):
        conn = open_db(tmp_db)
        index_session(conn, _make_sf(sample_session_path, 'sess-aaa'))
        results = search(conn, 'redis', exclude_sessions={'sess-aaa'})
        assert len(results) == 0
        close_db(conn)

    def test_limit(self, tmp_db, sample_session_path, compressed_session_path):
        conn = open_db(tmp_db)
        index_session(conn, _make_sf(sample_session_path, 'sess-aaa'))
        index_session(conn, _make_sf(compressed_session_path, 'sess-bbb'))
        results = search(conn, 'the', limit=1)
        assert len(results) <= 1
        close_db(conn)

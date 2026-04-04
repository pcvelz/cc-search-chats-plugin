"""Adaptive search engine — FTS5 primary with regex/LIKE fallback.

Simple keyword queries go through SQLite FTS5 for BM25-ranked results.
Regex patterns (grep-style \\| OR, .*, brackets) fall back to a
scan with Python regex matching over indexed content.
"""
import re
import sqlite3

from search_chat.database import search_sessions_aggregate

_REGEX_CHARS = re.compile(r'[\\.*+?\[\]{}()|^$]')


def is_regex_query(query: str) -> bool:
    """Detect if a query contains regex metacharacters."""
    if query.startswith('"') and query.endswith('"'):
        return False
    return bool(_REGEX_CHARS.search(query))


def normalize_query(query: str) -> str:
    r"""Normalize BRE-style patterns to ERE/Python regex.
    Converts grep's \| (BRE OR) to | (ERE OR).
    """
    return query.replace('\\|', '|')


def _regex_search(
    conn: sqlite3.Connection,
    pattern: str,
    project_dir: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Fallback search using Python regex over indexed message content."""
    normalized = normalize_query(pattern)
    try:
        regex = re.compile(normalized, re.IGNORECASE)
    except re.error:
        regex = re.compile(re.escape(pattern), re.IGNORECASE)

    sql = 'SELECT m.session_id, m.content, m.timestamp FROM message m'
    params: list = []
    if project_dir is not None:
        sql += ' JOIN session s ON m.session_id = s.session_id WHERE s.project_dir = ?'
        params.append(project_dir)

    rows = conn.execute(sql, params).fetchall()

    session_hits: dict[str, dict] = {}
    for row in rows:
        sid = row['session_id']
        content = row['content']
        if regex.search(content):
            if sid not in session_hits:
                match = regex.search(content)
                start = max(0, match.start() - 40)
                end = min(len(content), match.end() + 40)
                snippet = '...' + content[start:end] + '...'
                session_hits[sid] = {
                    'session_id': sid,
                    'match_count': 0,
                    'snippet': snippet,
                    'latest_timestamp': row['timestamp'],
                    'best_score': 0.0,
                }
            session_hits[sid]['match_count'] += 1
            if row['timestamp'] > session_hits[sid]['latest_timestamp']:
                session_hits[sid]['latest_timestamp'] = row['timestamp']

    results = sorted(session_hits.values(), key=lambda x: x['match_count'], reverse=True)
    return results[:limit]


def search(
    conn: sqlite3.Connection,
    query: str,
    project_dir: str | None = None,
    exclude_sessions: set[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Adaptive search: tries FTS5 first, falls back to regex for complex patterns.
    Returns list of dicts with: session_id, match_count, snippet, latest_timestamp.
    """
    exclude = exclude_sessions or set()

    if is_regex_query(query):
        results = _regex_search(conn, query, project_dir, limit + len(exclude))
    else:
        fts_results = search_sessions_aggregate(conn, query, project_dir, limit + len(exclude))
        if fts_results:
            results = [dict(r) for r in fts_results]
        else:
            results = _regex_search(conn, re.escape(query), project_dir, limit + len(exclude))

    results = [r for r in results if r['session_id'] not in exclude]
    return results[:limit]

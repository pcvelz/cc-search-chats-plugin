"""Adaptive search engine — FTS5 primary with regex/LIKE fallback.

Simple keyword queries go through SQLite FTS5 for BM25-ranked results.
Regex patterns (grep-style \\| OR, .*, brackets) fall back to a
scan with Python regex matching over indexed content.
"""
import re
import sqlite3

from search_chat.database import search_sessions_aggregate

# A bare '.' is deliberately NOT a regex signal: it appears in far more file
# names ("config.php", "search_chat.lister") than regex wildcards, and those
# must reach FTS5 (a quoted phrase matches them exactly) rather than the
# full-table Python regex scan. ".*" still routes to regex via '*'.
_REGEX_CHARS = re.compile(r'[\\*+?\[\]{}()|^$]')
_FTS_OPERATORS = frozenset({'AND', 'OR', 'NOT'})
_HAS_TOKEN_CHAR = re.compile(r'\w')
_PREFIXABLE_WORD = re.compile(r'^[A-Za-z]{4,}$')


def is_regex_query(query: str) -> bool:
    """Detect if a query contains regex metacharacters."""
    if query.startswith('"') and query.endswith('"'):
        return False
    return bool(_REGEX_CHARS.search(query))


def build_fts_query(query: str) -> str:
    """Turn a plain-text query into a safe FTS5 MATCH expression.

    Each whitespace-separated word becomes a quoted phrase, so punctuation that
    FTS5 would otherwise parse as syntax ("SWISS-2665", "foo:bar", "a/b") is
    tokenized inside the phrase instead of raising a syntax error. Before this,
    such a query produced no FTS result and fell through to the Python regex
    scan over every indexed message (12s across all projects vs 2s).

    Plain alphabetic words of 4+ chars get a trailing '*' so "deploy" also
    finds "deployment" and "migrat" finds "migration" - the fuzziness the
    /find-chat flow relies on, at negligible query cost. Identifiers (digits,
    mixed tokens) stay exact so "2665" does not match "26650". Words with no
    token characters at all are dropped (an empty phrase matches nothing and
    would poison the implicit AND). Bare uppercase AND/OR/NOT keep their
    operator meaning; a query already wrapped in double quotes is passed
    through as a single exact phrase.
    """
    stripped = query.strip()
    if len(stripped) >= 2 and stripped.startswith('"') and stripped.endswith('"'):
        return stripped
    parts: list[str] = []
    for word in stripped.split():
        if word in _FTS_OPERATORS:
            parts.append(word)
        elif _HAS_TOKEN_CHAR.search(word):
            phrase = '"' + word.replace('"', '""') + '"'
            parts.append(phrase + '*' if _PREFIXABLE_WORD.match(word) else phrase)
    return ' '.join(parts)


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


def _like_escape(literal: str) -> str:
    return literal.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _literal_search(
    conn: sqlite3.Connection,
    literal: str,
    project_dir: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Case-insensitive substring fallback for a plain query FTS5 found nothing for.

    Catches what token matching cannot: a query that is the tail or middle of
    a word ("ploy" in "deploy"). Runs as a SQLite LIKE scan inside the engine
    (1.3s over 1.1M messages) instead of fetching every row into Python for a
    regex (7.4s), so a miss across all projects stays cheap. Snippets are
    fetched per returned session via the session index.
    """
    pattern = '%' + _like_escape(literal) + '%'
    sql = (
        'SELECT m.session_id, COUNT(*) AS match_count, MAX(m.timestamp) AS latest_timestamp '
        'FROM message m'
    )
    params: list = []
    if project_dir is not None:
        sql += ' JOIN session s ON m.session_id = s.session_id'
    sql += " WHERE m.content LIKE ? ESCAPE '\\'"
    params.append(pattern)
    if project_dir is not None:
        sql += ' AND s.project_dir = ?'
        params.append(project_dir)
    sql += ' GROUP BY m.session_id ORDER BY match_count DESC LIMIT ?'
    params.append(limit)

    results = []
    for row in conn.execute(sql, params).fetchall():
        content_row = conn.execute(
            "SELECT content FROM message WHERE session_id = ? AND content LIKE ? ESCAPE '\\' LIMIT 1",
            (row['session_id'], pattern),
        ).fetchone()
        content = content_row['content'] if content_row else ''
        at = content.lower().find(literal.lower())
        start = max(0, at - 40)
        end = min(len(content), at + len(literal) + 40)
        results.append({
            'session_id': row['session_id'],
            'match_count': row['match_count'],
            'snippet': '...' + content[start:end] + '...',
            'latest_timestamp': row['latest_timestamp'],
            'best_score': 0.0,
        })
    return results


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
        results = search_sessions_aggregate(
            conn, build_fts_query(query), project_dir, limit + len(exclude),
        )
        if not results:
            results = _literal_search(conn, query, project_dir, limit + len(exclude))

    results = [r for r in results if r['session_id'] not in exclude]
    return results[:limit]

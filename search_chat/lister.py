"""Build a compact, recency-ranked index of recent sessions for /find-chat.

This is the thin "which session do I mean?" bridge — NOT full-text search.
Topic matching is a shallow scan of each session's opening messages; when it
finds nothing the caller should fall back to /search-chat. All functions are
pure and DB-free.
"""
import re

from search_chat.parser import extract_session_title, parse_session
from search_chat.types import ParsedMessage, SessionFile, SessionListItem

# Conversational noise that should never count as a topic term.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "we", "us",
    "i", "you", "it", "is", "was", "were", "be", "that", "this", "these",
    "those", "where", "when", "what", "which", "who", "did", "do", "does",
    "had", "have", "has", "about", "with", "from", "our", "my", "your",
    "last", "recent", "recently", "earlier", "previous", "old", "back",
    "chat", "chats", "session", "sessions", "conversation", "conversations",
    "discuss", "discussed", "discussing", "talked", "talk", "talking",
    "find", "get", "show", "pull", "open", "look", "go", "see", "want",
    "one", "ago", "time", "yesterday", "today", "week", "day",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_HEAD_MESSAGES = 40
_SCAN_CAP = 500


def topic_tokens(topic: str) -> list[str]:
    """Lowercase, split into alphanumeric tokens, drop stopwords and len<3."""
    tokens = _TOKEN_RE.findall(topic.lower())
    return [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS]


def _session_head_text(file_path: str, max_messages: int = _HEAD_MESSAGES) -> str:
    """Lowercased concatenation of the first max_messages parsed messages."""
    parts: list[str] = []
    count = 0
    for rec in parse_session(file_path):
        if isinstance(rec, ParsedMessage):
            parts.append(rec.content)
            count += 1
            if count >= max_messages:
                break
    return "\n".join(parts).lower()


def score_session(file_path: str, tokens: list[str]) -> int:
    """Count how many distinct topic tokens appear in the session's opening messages."""
    if not tokens:
        return 0
    text = _session_head_text(file_path)
    return sum(1 for t in set(tokens) if t in text)


def build_list_items(
    session_files: list[SessionFile],
    topic: str = "",
    limit: int = 3,
    title_chars: int = 100,
    scan_cap: int = _SCAN_CAP,
) -> list[SessionListItem]:
    """Build a recency-ranked list of SessionListItem, optionally topic-filtered.

    With no usable topic tokens: the newest `limit` sessions (session_files is
    assumed already sorted newest-first). With a topic: keep only sessions whose
    opening messages mention at least one topic token, ranked by (match score
    desc, recency desc), capped at `limit`. Only the first `scan_cap` newest
    sessions are scored, to bound cost on --all-projects.
    """
    tokens = topic_tokens(topic)
    candidates = session_files[:scan_cap] if tokens else session_files

    scored: list[tuple[int, SessionFile]] = []
    for sf in candidates:
        if tokens:
            score = score_session(sf.file_path, tokens)
            if score == 0:
                continue
        else:
            score = 0
        scored.append((score, sf))

    # Input is newest-first; a stable sort by score keeps recency as the tiebreak.
    # With no topic every score is 0 => pure recency order is preserved.
    scored.sort(key=lambda pair: pair[0], reverse=True)

    return [
        SessionListItem(
            session_id=sf.session_id,
            title=extract_session_title(sf.file_path, max_chars=title_chars),
            project_dir=sf.project_dir,
            mtime=sf.mtime,
        )
        for _score, sf in scored[:limit]
    ]

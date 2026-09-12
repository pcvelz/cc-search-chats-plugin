"""Build a compact, recency-ranked index of recent sessions for /find-chat.

This is the thin "which session do I mean?" bridge — NOT full-text search.
Topic matching is a shallow scan of each session's opening messages; when it
finds nothing the caller should fall back to /search-chat. All functions are
pure and DB-free.
"""
import re

from search_chat.parser import (
    extract_custom_title, extract_session_title, parse_session, truncate_title,
)
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


def score_session(file_path: str, tokens: list[str], custom_title: str | None = None) -> int:
    """Count how many distinct topic tokens appear in the session's opening
    messages or in `custom_title` (the /rename title), so renamed sessions
    with a generic opening prompt still match. The caller passes the title in,
    untruncated, so each file is read for it exactly once."""
    if not tokens:
        return 0
    text = _session_head_text(file_path)
    if custom_title:
        text += "\n" + custom_title.lower()
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
    opening messages or custom title (/rename) mention at least one topic
    token, ranked by (match score desc, recency desc), capped at `limit`. Only
    the first `scan_cap` newest sessions are scored, to bound cost on
    --all-projects. The listed title is the custom title when set, else the
    opening prompt.
    """
    tokens = topic_tokens(topic)

    # Each candidate's custom title is read once, untruncated, and carried
    # through to display: scoring must see the whole title (a token past the
    # display cut-off still counts) and the file must not be scanned twice.
    if tokens:
        scored: list[tuple[int, SessionFile, str | None]] = []
        for sf in session_files[:scan_cap]:
            custom = extract_custom_title(sf.file_path, max_chars=None)
            score = score_session(sf.file_path, tokens, custom)
            if score > 0:
                scored.append((score, sf, custom))
        # Input is newest-first; a stable sort by score keeps recency as the tiebreak.
        scored.sort(key=lambda entry: entry[0], reverse=True)
        picked = [(sf, custom) for _score, sf, custom in scored[:limit]]
    else:
        picked = [
            (sf, extract_custom_title(sf.file_path, max_chars=None))
            for sf in session_files[:limit]
        ]

    return [
        SessionListItem(
            session_id=sf.session_id,
            title=truncate_title(custom, title_chars) if custom
            else extract_session_title(sf.file_path, max_chars=title_chars),
            project_dir=sf.project_dir,
            mtime=sf.mtime,
        )
        for sf, custom in picked
    ]

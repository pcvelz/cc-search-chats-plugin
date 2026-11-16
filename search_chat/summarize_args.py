"""Binary mode classifier for /summarize-chat arguments.

The contract is deliberately binary and deterministic so the main agent never
has to judge whether trailing text "counts":

- ``show``   - the arguments are ONLY session id(s), flags, repeated command
               names, list separators and status-bar chrome. The summary is
               the deliverable and is relayed into chat.
- ``silent`` - ANY other text is present. That text is an instruction to the
               main agent; the summary is private context and must NOT be
               pasted into chat.

Usage: ``search-chat.sh --classify-summarize`` reads the raw arguments on
stdin (heredoc-safe for any quoting) and prints one JSON object.
"""
import json
import re
import sys

_ID = re.compile(
    r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|(?<![a-z0-9])[a-f0-9]{8}(?![a-z0-9-])',
    re.IGNORECASE,
)
_COMMAND = re.compile(r'^/?(?:search-chats:)?summarize-chat$', re.IGNORECASE)
_FLAGS = {'--detailed': 'detailed', '--eu': 'eu'}
# Pure list separators between ids ("x and y", "x, y", "x & y").
_SEPARATORS = {'and', 'en', '&', '+'}
# Status-bar chrome: single-letter labels like "S:" and pure punctuation runs.
_CHROME_LABEL = re.compile(r'^[a-z]:$', re.IGNORECASE)
_EDGE_PUNCT = ',.;!?()[]{}|"\'`'


def classify(text: str) -> dict:
    session_ids: list[str] = []
    for m in _ID.finditer(text):
        sid = m.group(0).lower()
        if sid not in session_ids:
            session_ids.append(sid)

    flag = 'default'
    residual: list[str] = []
    stripped = _ID.sub(' ', text)
    for raw in stripped.split():
        if raw.lower() in _FLAGS:
            flag = _FLAGS[raw.lower()]
            continue
        tok = raw.strip(_EDGE_PUNCT)
        low = tok.lower()
        if low in _FLAGS:
            flag = _FLAGS[low]
            continue
        if not tok or not re.search(r'[a-z0-9]', tok, re.IGNORECASE):
            continue  # pure punctuation / box-drawing chrome
        if _COMMAND.match(tok) or low in _SEPARATORS or _CHROME_LABEL.match(tok):
            continue
        residual.append(raw)

    return {
        'mode': 'silent' if residual else 'show',
        'session_ids': session_ids,
        'flag': flag,
        'residual': ' '.join(residual),
    }


def main() -> None:
    print(json.dumps(classify(sys.stdin.read())))

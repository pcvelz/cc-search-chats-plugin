#!/usr/bin/env python3
"""Stub: Extract session ID from messy text (status bar copy-paste, etc.)."""
import re
import sys

EMBEDDED_UUID_FULL = re.compile(
    r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}',
    re.IGNORECASE,
)
EMBEDDED_UUID_SHORT = re.compile(r'(?<![a-f0-9])[a-f0-9]{8}(?![a-f0-9])', re.IGNORECASE)


def extract_session_id(text: str) -> str:
    """Scan text for an embedded session ID (full UUID or 8-char short)."""
    m = EMBEDDED_UUID_FULL.search(text)
    if m:
        return m.group(0).lower()
    m = EMBEDDED_UUID_SHORT.search(text)
    if m:
        return m.group(0).lower()
    return ''


def clean_query(text: str, session_id: str) -> str:
    """Remove session ID from text and strip leftover separator artifacts."""
    cleaned = text.replace(session_id, '', 1)
    cleaned = re.sub(r'^[\s|:\-\[\]/█░]+', '', cleaned)
    cleaned = re.sub(r'[\s|:\-\[\]/█░]+$', '', cleaned)
    return cleaned


if __name__ == '__main__':
    text = sys.argv[1] if len(sys.argv) > 1 else 'S: a1b2c3d4 | C: [█░░░] 265k/1M | D5/7: On Pace'
    session_id = extract_session_id(text)
    if session_id:
        query = clean_query(text, session_id)
        print(f'extracted_session: {session_id}')
        print(f'remaining_query:   {query!r}')
    else:
        print('No session ID found')

"""Text and JSON output formatters. Pure functions — no I/O."""
import datetime
import json


def format_search_results_text(results: list[dict]) -> str:
    if not results:
        return 'No matches found.'
    lines = [f'Found {len(results)} session(s) with matches:', '']
    for i, r in enumerate(results, 1):
        sid = r['session_id']
        short = sid[:8]
        count = r['match_count']
        ts = r.get('latest_timestamp', '')
        lines.append(f'{i}. [{short}] - {count} matches - {ts}')
        lines.append(f'   Full ID: {sid}')
        lines.append(f'   Resume: claude --resume {sid}')
        lines.append('')
    lines.append('Tip: Use --extract <id> to extract a specific session')
    lines.append('Tip: Use --extract-matches to auto-extract search results')
    return '\n'.join(lines)


def format_search_results_json(results: list[dict]) -> str:
    clean = []
    for r in results:
        clean.append({
            'session_id': r['session_id'],
            'match_count': r['match_count'],
            'snippet': r.get('snippet', ''),
            'timestamp': r.get('latest_timestamp', ''),
        })
    return json.dumps(clean, indent=2, ensure_ascii=False)


def format_extraction_json(session_id: str, messages: list[dict], epochs: list[dict] | None = None) -> str:
    msg_list = []
    for m in messages:
        msg_list.append({
            'role': m['role'],
            'content': m['content'],
            'timestamp': m['timestamp'],
            'epoch': m.get('epoch', 0),
        })
    result = {'session_id': session_id, 'messages': msg_list}
    if epochs:
        result['epochs'] = [dict(e) for e in epochs]
    return json.dumps(result, indent=2, ensure_ascii=False)


def _format_mtime(mtime: float) -> str:
    """Render an epoch mtime as a local 'YYYY-MM-DD HH:MM' string."""
    return datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


def format_session_list_text(items: list, scope_label: str) -> str:
    """Render candidate sessions for /find-chat. Thin: id, date, opening prompt."""
    if not items:
        return (
            f"No candidate sessions found ({scope_label}).\n"
            "Tip: broaden with --all-projects, or use /search-chat for full-text search."
        )
    lines = [f"Candidate sessions ({scope_label}) — newest first:", ""]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. [{it.session_id[:8]}] {_format_mtime(it.mtime)}")
        lines.append(f"   {it.title}")
        lines.append(f"   Full ID: {it.session_id}")
        lines.append("")
    lines.append("If one candidate clearly matches, continue in the same turn:")
    lines.append("/summarize-chat <id> (recap/question) or /search-chat <id> (content).")
    lines.append("Confirm with the user only when the candidates are genuinely ambiguous.")
    return "\n".join(lines)


def format_session_list_json(items: list) -> str:
    """JSON form of the candidate list."""
    clean = [
        {
            "session_id": it.session_id,
            "title": it.title,
            "project_dir": it.project_dir,
            "timestamp": _format_mtime(it.mtime),
        }
        for it in items
    ]
    return json.dumps(clean, indent=2, ensure_ascii=False)

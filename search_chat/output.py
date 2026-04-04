"""Text and JSON output formatters. Pure functions — no I/O."""
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

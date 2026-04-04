"""Main entry point — orchestrates search, extraction, and output."""
import os
import sys
from pathlib import Path

from search_chat.args import parse_args
from search_chat.database import (
    close_db, get_session_epochs, get_session_messages,
    index_session, jit_reindex, open_db,
)
from search_chat.engine import search
from search_chat.extractor import (
    build_extraction_lines, format_archive_footer, format_archive_header,
)
from search_chat.finder import (
    encode_project_path, find_current_session, get_project_dir,
    list_session_files, resolve_session_id, CLAUDE_PROJECTS_BASE,
)
from search_chat.output import (
    format_extraction_json, format_search_results_json, format_search_results_text,
)
from search_chat.types import SessionFile


def main():
    args = parse_args()
    project_path = args.project_path or os.getcwd()
    project_dir = get_project_dir(project_path)
    project_dir_name = encode_project_path(project_path)

    if not args.include_self and not args.exclude_session and project_dir.is_dir():
        current = find_current_session(project_dir)
        if current:
            args.exclude_session = current

    if args.read_result_session:
        _handle_read_result(args, project_dir)
        return

    if args.list_results_session:
        _handle_list_results(args, project_dir)
        return

    if not args.query and not args.extract_session:
        print('Error: No search query or session ID provided', file=sys.stderr)
        print('Usage: search-chat.sh <query> [--extract ID] [--extract-matches]', file=sys.stderr)
        sys.exit(1)

    conn = open_db()
    try:
        session_files = list_session_files(project_dir, include_agents=args.include_agents)
        jit_reindex(conn, session_files)

        if args.extract_session:
            _handle_extract(args, conn, project_dir, project_dir_name)
        else:
            _handle_search(args, conn, project_dir, project_dir_name)
    finally:
        close_db(conn)


def _handle_extract(args, conn, project_dir, project_dir_name):
    if args.exclude_session and args.extract_session.startswith(args.exclude_session):
        print(f'Session {args.extract_session} is excluded (current session).')
        return

    file_path, resolved_id = resolve_session_id(args.extract_session, project_dir)
    if file_path is None:
        if args.auto_detected_uuid:
            print(f"Note: '{args.extract_session}' did not match any session. Searching as text.", file=sys.stderr)
            args.query = args.original_query
            args.extract_session = ''
            _handle_search(args, conn, project_dir, project_dir_name)
            return
        print(resolved_id, file=sys.stderr)
        sys.exit(1)

    if resolved_id != args.extract_session:
        print(f'Resolved partial ID to: {resolved_id}', file=sys.stderr)

    if args.query:
        word_count = len(args.query.split())
        if word_count > 4:
            print(f'Instruction: {args.query}', file=sys.stderr)
            print('(full session extracted — filter skipped for LLM interpretation)', file=sys.stderr)
            args.query = ''

    messages = get_session_messages(conn, resolved_id)
    if not messages:
        sf = SessionFile(
            session_id=resolved_id, file_path=file_path,
            project_dir=project_dir_name,
            mtime=Path(file_path).stat().st_mtime,
            size=Path(file_path).stat().st_size,
        )
        index_session(conn, sf)
        messages = get_session_messages(conn, resolved_id)

    msg_dicts = [dict(m) for m in messages]

    if args.json:
        epochs = get_session_epochs(conn, resolved_id)
        epoch_dicts = [dict(e) for e in epochs] if epochs else None
        print(format_extraction_json(resolved_id, msg_dicts, epoch_dicts))
    else:
        lines = build_extraction_lines(
            msg_dicts, query=args.query or None,
            context_lines=args.context_lines,
            tail_lines=args.tail_lines, max_lines=args.max_lines,
        )
        print(format_archive_header(
            resolved_id, project=project_dir_name, query=args.query,
            context_lines=args.context_lines, tail_lines=args.tail_lines,
        ))
        for line in lines:
            print(line)
        print(format_archive_footer())


def _handle_search(args, conn, project_dir, project_dir_name):
    exclude = set()
    if args.exclude_session:
        exclude.add(args.exclude_session)

    dir_filter = None if args.all_projects else project_dir_name

    results = search(conn, args.query, project_dir=dir_filter,
                     exclude_sessions=exclude, limit=args.limit)

    if args.json:
        print(format_search_results_json(results))
    else:
        print(f'Query: {args.query}')
        print(f'Searching in: {project_dir}')
        print()
        print(format_search_results_text(results))

    if args.extract_matches and results:
        if not args.json:
            print()
            print('=' * 40)
            print(f'EXTRACTING TOP {args.extract_limit} MATCHES')
            print('=' * 40)
            print()

        for i, r in enumerate(results[:args.extract_limit]):
            sid = r['session_id']
            messages = get_session_messages(conn, sid)
            msg_dicts = [dict(m) for m in messages]

            if args.json:
                epochs = get_session_epochs(conn, sid)
                epoch_dicts = [dict(e) for e in epochs] if epochs else None
                print(format_extraction_json(sid, msg_dicts, epoch_dicts))
            else:
                print(f'[{i + 1}/{args.extract_limit}] Extracting: {sid}')
                lines = build_extraction_lines(msg_dicts, query=args.query or None, max_lines=args.max_lines)
                print(format_archive_header(sid, project=project_dir_name, query=args.query))
                for line in lines:
                    print(line)
                print(format_archive_footer())
                print()


def _handle_read_result(args, project_dir):
    session_dir = _find_session_dir(args.read_result_session, project_dir)
    if not session_dir:
        print(f'ERROR: Session {args.read_result_session} not found', file=sys.stderr)
        sys.exit(1)
    path = session_dir / 'tool-results' / args.read_result_file
    if path.is_file():
        print(path.read_text(encoding='utf-8', errors='replace'))
    else:
        print(f'ERROR: Tool result file not found: {args.read_result_file}', file=sys.stderr)
        sys.exit(1)


def _handle_list_results(args, project_dir):
    session_dir = _find_session_dir(args.list_results_session, project_dir)
    if not session_dir:
        print(f'ERROR: Session {args.list_results_session} not found', file=sys.stderr)
        sys.exit(1)
    print(f'=== Session: {session_dir.name} ===')
    print()
    print('--- Tool Results ---')
    tr = session_dir / 'tool-results'
    if tr.is_dir():
        for f in sorted(tr.iterdir()):
            print(f'  {f.name}  ({f.stat().st_size} bytes)')
    else:
        print('(no tool-results directory)')
    print()
    print('--- Subagents ---')
    sa = session_dir / 'subagents'
    if sa.is_dir():
        for f in sorted(sa.iterdir()):
            print(f'  {f.name}')
    else:
        print('(no subagents directory)')


def _find_session_dir(session_id: str, project_dir: Path) -> Path | None:
    candidate = project_dir / session_id
    if candidate.is_dir():
        return candidate
    if project_dir.is_dir():
        for d in project_dir.iterdir():
            if d.is_dir() and d.name.startswith(session_id):
                return d
    if CLAUDE_PROJECTS_BASE.is_dir():
        for proj in CLAUDE_PROJECTS_BASE.iterdir():
            if not proj.is_dir():
                continue
            for d in proj.iterdir():
                if d.is_dir() and d.name.startswith(session_id):
                    return d
    return None


if __name__ == '__main__':
    main()

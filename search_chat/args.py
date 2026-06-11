"""CLI argument parsing — preserves all v1.x flags plus new --json."""
import re
import sys
from dataclasses import dataclass


UUID_FULL = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
UUID_PARTIAL = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{1,4}[a-f0-9-]*$')
UUID_SHORT = re.compile(r'^[a-f0-9]{8}$')

# Embedded full-UUID detection — safe because full UUIDs never collide with prose
EMBEDDED_UUID_FULL = re.compile(
    r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}',
    re.IGNORECASE,
)


@dataclass
class Args:
    query: str = ''
    limit: int = 10
    extract_session: str = ''
    extract_matches: bool = False
    extract_limit: int = 5
    max_lines: int = 500
    context_lines: int = 0
    tail_lines: int = 0
    project_path: str = ''
    all_projects: bool = False
    list_mode: bool = False
    include_agents: bool = False
    exclude_session: str = ''
    include_self: bool = False
    json: bool = False
    read_result_session: str = ''
    read_result_file: str = ''
    list_results_session: str = ''
    auto_detected_uuid: bool = False
    original_query: str = ''


def _extract_embedded_uuid(text: str) -> str:
    """Scan text for an embedded full UUID. Return empty if none."""
    m = EMBEDDED_UUID_FULL.search(text)
    if m:
        return m.group(0).lower()
    return ''


def _clean_query_after_uuid_removal(query: str, uuid: str) -> str:
    """Remove UUID from query and discard status-bar chrome around it."""
    cleaned = query.replace(uuid, ' ', 1)
    # Split on status-bar separator runs and drop common single-letter chrome labels
    tokens = re.split(r'[\s|:\-\[\]█░]+', cleaned)
    noise = {'s', 'c', 'd', 'm'}
    tokens = [t for t in tokens if t and t.lower() not in noise]
    return ' '.join(tokens)


def parse_args(argv: list[str] | None = None) -> Args:
    if argv is None:
        argv = sys.argv[1:]

    args = Args()
    query_parts: list[str] = []
    i = 0

    while i < len(argv):
        arg = argv[i]
        if arg in ('--help', '-h'):
            _print_help()
            sys.exit(0)
        elif arg == '--limit' and i + 1 < len(argv):
            args.limit = int(argv[i + 1]); i += 2
        elif arg == '--extract' and i + 1 < len(argv):
            args.extract_session = argv[i + 1]; i += 2
        elif arg == '--extract-matches':
            args.extract_matches = True; i += 1
        elif arg == '--extract-limit' and i + 1 < len(argv):
            args.extract_limit = int(argv[i + 1]); i += 2
        elif arg == '--max-lines' and i + 1 < len(argv):
            args.max_lines = int(argv[i + 1]); i += 2
        elif arg == '--context' and i + 1 < len(argv):
            args.context_lines = int(argv[i + 1]); i += 2
        elif arg == '--tail' and i + 1 < len(argv):
            args.tail_lines = int(argv[i + 1]); i += 2
        elif arg == '--project' and i + 1 < len(argv):
            args.project_path = argv[i + 1]; i += 2
        elif arg == '--all-projects':
            args.all_projects = True; i += 1
        elif arg == '--list':
            args.list_mode = True; i += 1
        elif arg == '--include-agents':
            args.include_agents = True; i += 1
        elif arg == '--exclude-session' and i + 1 < len(argv):
            args.exclude_session = argv[i + 1]; i += 2
        elif arg == '--include-self':
            args.include_self = True; i += 1
        elif arg == '--json':
            args.json = True; i += 1
        elif arg == '--read-result' and i + 2 < len(argv):
            args.read_result_session = argv[i + 1]
            args.read_result_file = argv[i + 2]; i += 3
        elif arg == '--list-results' and i + 1 < len(argv):
            args.list_results_session = argv[i + 1]; i += 2
        elif arg.startswith('--'):
            print(f"Warning: Unknown option '{arg}' (ignored)", file=sys.stderr)
            i += 1
        else:
            query_parts.append(arg); i += 1

    args.query = ' '.join(query_parts)
    args.original_query = args.query

    # Self-heal: an ID-shaped query in --list mode is a misrouted extraction
    # (e.g. an agent invoking /find-chat with a session id + --tail). The list
    # matches topic words against session openings, so an id can never match —
    # flip to extraction instead of returning a useless empty list. Short bare
    # 8-hex only flips when extraction-shaped flags accompany it, so a genuine
    # hex-looking topic word still lists.
    if args.list_mode and args.query and not args.extract_session:
        words = args.query.split()
        first = words[0]
        extractish = args.tail_lines > 0 or any(
            w in ('--tail', '--max-lines', '--context', '--extract-matches') for w in words[1:]
        )
        if UUID_FULL.match(first) or UUID_PARTIAL.match(first) or (UUID_SHORT.match(first) and extractish):
            args.list_mode = False
            print('Note: query is a session id, not a topic — switched --list to extraction '
                  '(--list takes topic words; session ids go straight to extraction).',
                  file=sys.stderr)

    if args.query and not args.extract_session and not args.list_mode:
        words = args.query.split()
        first = words[0] if words else ''
        # First token is a session ID (full, partial, or short 8-hex). Short bare
        # hex is accepted even with trailing words — that powers the documented
        # `search-chat <short-id> <filter>` form. A non-session 8-hex collision
        # (e.g. "deadbeef is slang") self-heals: __main__ falls back to a text
        # search of original_query when the ID resolves to no session.
        if UUID_FULL.match(first) or UUID_PARTIAL.match(first) or UUID_SHORT.match(first):
            args.extract_session = first
            args.auto_detected_uuid = True
            # Default --tail 200 for UUID extraction (unless explicitly set)
            if args.tail_lines == 0:
                args.tail_lines = 200
            remaining = words[1:]
            new_query_parts: list[str] = []
            j = 0
            while j < len(remaining):
                w = remaining[j]
                if w == '--tail' and j + 1 < len(remaining):
                    args.tail_lines = int(remaining[j + 1]); j += 2
                elif w == '--context' and j + 1 < len(remaining):
                    args.context_lines = int(remaining[j + 1]); j += 2
                elif w == '--max-lines' and j + 1 < len(remaining):
                    args.max_lines = int(remaining[j + 1]); j += 2
                elif w == '--extract-matches':
                    args.extract_matches = True; j += 1
                elif w == '--include-agents':
                    args.include_agents = True; j += 1
                elif w == '--include-self':
                    args.include_self = True; j += 1
                elif w == '--limit' and j + 1 < len(remaining):
                    args.limit = int(remaining[j + 1]); j += 2
                elif w == '--exclude-session' and j + 1 < len(remaining):
                    args.exclude_session = remaining[j + 1]; j += 2
                else:
                    new_query_parts.append(w); j += 1
            args.query = ' '.join(new_query_parts)

    # Second chance: embedded full UUID inside messy text (e.g. status bar copy-paste).
    # Short UUIDs are NOT scanned here to avoid false positives in prose.
    if args.query and not args.extract_session and not args.list_mode:
        embedded = _extract_embedded_uuid(args.query)
        if embedded:
            args.extract_session = embedded
            args.auto_detected_uuid = True
            if args.tail_lines == 0:
                args.tail_lines = 200
            args.query = _clean_query_after_uuid_removal(args.query, embedded)

    return args


def _print_help():
    print("""Usage: search-chat.sh <query|session-uuid> [OPTIONS]

Search through Claude Code chat history and extract conversations.
If a UUID is passed as query, it auto-extracts that session.

Search Options:
  --limit N          Maximum sessions to return (default: 10)
  --project PATH     Search in specific project (default: current directory)
  --all-projects     Search across all projects
  --list             List recent sessions (id, date, opening prompt) instead of searching
  --include-agents   Include subagent conversations (default: off)
  --include-self     Include current session in results
  --exclude-session ID  Exclude a specific session from results
  --json             Output results as JSON

Extraction Options:
  --extract ID       Extract conversation from specific session ID
  --extract-matches  Auto-extract from top search matches
  --extract-limit N  Number of matches to extract (default: 5)
  --max-lines N      Max lines per session extraction (default: 500)
  --context N        Messages of context around filter matches (default: 0)
  --tail N           Show only last N lines of extraction

Examples:
  search-chat.sh 'staging deploy'                     # Search only
  search-chat.sh --extract abc12345-...               # Extract specific session
  search-chat.sh 'ssh production' --extract-matches   # Search + extract top 5
  search-chat.sh 'redis' --json                       # JSON output""")

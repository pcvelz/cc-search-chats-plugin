"""CLI argument parsing — preserves all v1.x flags plus new --json."""
import re
import sys
from dataclasses import dataclass


UUID_FULL = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
UUID_PARTIAL = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{1,4}[a-f0-9-]*$')
UUID_SHORT = re.compile(r'^[a-f0-9]{8}$')


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
    include_agents: bool = False
    exclude_session: str = ''
    include_self: bool = False
    json: bool = False
    read_result_session: str = ''
    read_result_file: str = ''
    list_results_session: str = ''
    auto_detected_uuid: bool = False
    original_query: str = ''


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

    if args.query and not args.extract_session:
        words = args.query.split()
        first = words[0] if words else ''
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

    return args


def _print_help():
    print("""Usage: search-chat.sh <query|session-uuid> [OPTIONS]

Search through Claude Code chat history and extract conversations.
If a UUID is passed as query, it auto-extracts that session.

Search Options:
  --limit N          Maximum sessions to return (default: 10)
  --project PATH     Search in specific project (default: current directory)
  --all-projects     Search across all projects
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

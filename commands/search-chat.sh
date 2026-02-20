#!/bin/bash
# search-chat.sh - Search through Claude Code chat history for the current project
# Usage: search-chat.sh <query> [--limit N] [--extract ID] [--extract-matches] [--project PATH]

set -e

# Default values
LIMIT=10
EXTRACT_SESSION=""
EXTRACT_MATCHES=false
EXTRACT_LIMIT=5
MAX_LINES=500
CONTEXT_LINES=0
TAIL_LINES=0
PROJECT_PATH=""
QUERY=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --extract)
            EXTRACT_SESSION="$2"
            shift 2
            ;;
        --extract-matches)
            EXTRACT_MATCHES=true
            shift
            ;;
        --extract-limit)
            EXTRACT_LIMIT="$2"
            shift 2
            ;;
        --max-lines)
            MAX_LINES="$2"
            shift 2
            ;;
        --project)
            PROJECT_PATH="$2"
            shift 2
            ;;
        --read-result)
            READ_RESULT_SESSION="$2"
            READ_RESULT_FILE="$3"
            shift 3
            ;;
        --context)
            CONTEXT_LINES="${2:-3}"
            shift 2
            ;;
        --tail)
            TAIL_LINES="$2"
            shift 2
            ;;
        --list-results)
            LIST_RESULTS_SESSION="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: search-chat.sh <query|session-uuid> [OPTIONS]"
            echo ""
            echo "Search through Claude Code chat history and extract conversations."
            echo "If a UUID is passed as query, it auto-extracts that session."
            echo ""
            echo "Search Options:"
            echo "  --limit N          Maximum sessions to return (default: 10)"
            echo "  --project PATH     Search in specific project (default: current directory)"
            echo ""
            echo "Extraction Options:"
            echo "  --extract ID       Extract conversation from specific session ID"
            echo "  --extract-matches  Auto-extract from top search matches"
            echo "  --extract-limit N  Number of matches to extract (default: 5)"
            echo "  --max-lines N      Max lines per session extraction (default: 500)"
            echo "  --context N        Messages of context around filter matches (default: 0)"
            echo "  --tail N           Show only last N lines of extraction"
            echo ""
            echo "Examples:"
            echo "  search-chat.sh 'staging deploy'                     # Search only"
            echo "  search-chat.sh --extract abc12345-...               # Extract specific session"
            echo "  search-chat.sh 'ssh production' --extract-matches   # Search + extract top 5"
            echo "  search-chat.sh 'redis' --project /path/to/proj      # Search other project"
            exit 0
            ;;
        *)
            if [[ "$1" =~ ^-- ]]; then
                echo "Warning: Unknown option '$1' (ignored)" >&2
                shift
            else
                if [[ -z "$QUERY" ]]; then
                    QUERY="$1"
                else
                    QUERY="$QUERY $1"
                fi
                shift
            fi
            ;;
    esac
done

# Auto-detect: if query starts with a UUID (full or partial), split it from remaining text
# Remaining text becomes a filter query within the extracted session
UUID_FULL_REGEX='^([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})([ ,]+(.*))?$'
UUID_PARTIAL_REGEX='^([a-f0-9]{8}-[a-f0-9]{1,4}[a-f0-9-]*)([ ,]+(.*))?$'
UUID_SHORT_REGEX='^([a-f0-9]{8})([ ,]+(.*))?$'
if [[ -n "$QUERY" ]] && [[ -z "$EXTRACT_SESSION" ]]; then
    if [[ "$QUERY" =~ $UUID_FULL_REGEX ]] || [[ "$QUERY" =~ $UUID_PARTIAL_REGEX ]] || [[ "$QUERY" =~ $UUID_SHORT_REGEX ]]; then
        EXTRACT_SESSION="${BASH_REMATCH[1]}"
        QUERY="${BASH_REMATCH[3]}"
    fi
fi

# Validate: need either query, extract session, or one of the result modes
if [[ -z "$QUERY" ]] && [[ -z "$EXTRACT_SESSION" ]] && [[ -z "${READ_RESULT_SESSION:-}" ]] && [[ -z "${LIST_RESULTS_SESSION:-}" ]]; then
    echo "Error: No search query or session ID provided"
    echo "Usage: search-chat.sh <query> [--extract ID] [--extract-matches]"
    exit 1
fi

# Create temp file for results
RESULTS_FILE=$(mktemp)
trap 'rm -f "$RESULTS_FILE"' EXIT

# Determine project path
if [[ -n "$PROJECT_PATH" ]]; then
    TARGET_PATH="$PROJECT_PATH"
else
    TARGET_PATH=$(pwd)
fi

# Convert to Claude projects path format
CLAUDE_PROJECT_DIR=$(echo "$TARGET_PATH" | sed 's|^/|-|' | sed 's|/|-|g')
CLAUDE_PROJECTS_BASE="$HOME/.claude/projects"
PROJECT_HISTORY_DIR="$CLAUDE_PROJECTS_BASE/$CLAUDE_PROJECT_DIR"

# =====================================================================
# Mode: Read specific tool result from a session
# =====================================================================
if [[ -n "${READ_RESULT_SESSION:-}" ]]; then
  SESSION_DIR=""
  # Try current project first
  if [[ -d "$PROJECT_HISTORY_DIR/$READ_RESULT_SESSION" ]]; then
    SESSION_DIR="$PROJECT_HISTORY_DIR/$READ_RESULT_SESSION"
  else
    # Try partial match in current project
    MATCH=$(find "$PROJECT_HISTORY_DIR" -maxdepth 1 -type d -name "${READ_RESULT_SESSION}*" 2>/dev/null | head -1)
    if [[ -n "$MATCH" ]]; then
      SESSION_DIR="$MATCH"
    else
      # Search all projects
      SESSION_DIR=$(find "$CLAUDE_PROJECTS_BASE" -maxdepth 2 -type d -name "${READ_RESULT_SESSION}*" 2>/dev/null | head -1)
    fi
  fi

  if [[ -z "$SESSION_DIR" ]]; then
    echo "ERROR: Session $READ_RESULT_SESSION not found" >&2
    exit 1
  fi

  RESULT_FILE="$SESSION_DIR/tool-results/$READ_RESULT_FILE"
  if [[ -f "$RESULT_FILE" ]]; then
    cat "$RESULT_FILE"
  else
    echo "ERROR: Tool result file not found: $READ_RESULT_FILE" >&2
    echo "" >&2
    echo "Available files in $SESSION_DIR/tool-results/:" >&2
    ls "$SESSION_DIR/tool-results/" 2>/dev/null | head -20 >&2
    exit 1
  fi
  exit 0
fi

# =====================================================================
# Mode: List tool results and subagents for a session
# =====================================================================
if [[ -n "${LIST_RESULTS_SESSION:-}" ]]; then
  SESSION_DIR=""
  if [[ -d "$PROJECT_HISTORY_DIR/$LIST_RESULTS_SESSION" ]]; then
    SESSION_DIR="$PROJECT_HISTORY_DIR/$LIST_RESULTS_SESSION"
  else
    MATCH=$(find "$PROJECT_HISTORY_DIR" -maxdepth 1 -type d -name "${LIST_RESULTS_SESSION}*" 2>/dev/null | head -1)
    if [[ -n "$MATCH" ]]; then
      SESSION_DIR="$MATCH"
    else
      SESSION_DIR=$(find "$CLAUDE_PROJECTS_BASE" -maxdepth 2 -type d -name "${LIST_RESULTS_SESSION}*" 2>/dev/null | head -1)
    fi
  fi

  if [[ -z "$SESSION_DIR" ]]; then
    echo "ERROR: Session $LIST_RESULTS_SESSION not found" >&2
    exit 1
  fi

  echo "=== Session: $(basename "$SESSION_DIR") ==="
  echo ""
  echo "--- Tool Results ---"
  if [[ -d "$SESSION_DIR/tool-results" ]]; then
    ls -lh "$SESSION_DIR/tool-results/" 2>/dev/null | tail -n +2
  else
    echo "(no tool-results directory)"
  fi
  echo ""
  echo "--- Subagents ---"
  if [[ -d "$SESSION_DIR/subagents" ]]; then
    ls "$SESSION_DIR/subagents/" 2>/dev/null
  else
    echo "(no subagents directory)"
  fi
  exit 0
fi

# Function to find session file (supports partial UUIDs, searches all projects)
find_session_file() {
    local session_id="$1"

    # 1. Try exact match in current project
    local session_file="$PROJECT_HISTORY_DIR/$session_id.jsonl"
    if [[ -f "$session_file" ]]; then
        echo "$session_file"
        return 0
    fi

    # 2. Try exact match across all projects
    local found=$(find "$CLAUDE_PROJECTS_BASE" -name "$session_id.jsonl" -type f 2>/dev/null | head -1)
    if [[ -n "$found" ]]; then
        echo "$found"
        return 0
    fi

    # 3. Try partial/prefix match in current project
    local matches=()
    if [[ -d "$PROJECT_HISTORY_DIR" ]]; then
        while IFS= read -r f; do
            matches+=("$f")
        done < <(find "$PROJECT_HISTORY_DIR" -maxdepth 1 -name "${session_id}*.jsonl" -type f ! -name "agent-*" 2>/dev/null)
    fi

    if [[ ${#matches[@]} -eq 1 ]]; then
        echo "${matches[0]}"
        return 0
    elif [[ ${#matches[@]} -gt 1 ]]; then
        echo "AMBIGUOUS:${#matches[@]}" >&2
        for m in "${matches[@]}"; do
            echo "  $(basename "$m" .jsonl)" >&2
        done
        # Return the first match but signal ambiguity
        echo "${matches[0]}"
        return 2
    fi

    # 4. Try partial/prefix match across all projects
    matches=()
    while IFS= read -r f; do
        matches+=("$f")
    done < <(find "$CLAUDE_PROJECTS_BASE" -name "${session_id}*.jsonl" -type f ! -name "agent-*" 2>/dev/null)

    if [[ ${#matches[@]} -eq 1 ]]; then
        echo "${matches[0]}"
        return 0
    elif [[ ${#matches[@]} -gt 1 ]]; then
        echo "AMBIGUOUS:${#matches[@]}" >&2
        for m in "${matches[@]}"; do
            echo "  $(basename "$m" .jsonl)" >&2
        done
        echo "${matches[0]}"
        return 2
    fi

    return 1
}

# Function to extract conversation from session using Python
extract_session() {
    local session_file="$1"
    local max_lines="$2"
    local query="${3:-}"

    export SEARCH_SESSION_FILE="$session_file"
    export SEARCH_MAX_LINES="$max_lines"
    export SEARCH_QUERY="$query"
    export SEARCH_CONTEXT_LINES="$CONTEXT_LINES"
    export SEARCH_TAIL_LINES="$TAIL_LINES"

    python3 << 'PYTHON_SCRIPT'
import json
import sys
import os
from datetime import datetime

session_file = os.environ.get('SEARCH_SESSION_FILE', '')
max_lines = int(os.environ.get('SEARCH_MAX_LINES', '500'))
query = os.environ.get('SEARCH_QUERY', '').lower() or None
context_lines = int(os.environ.get('SEARCH_CONTEXT_LINES', '0'))
tail_lines = int(os.environ.get('SEARCH_TAIL_LINES', '0'))

def extract_text(content):
    """Extract readable text from message content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    texts.append(item.get('text', ''))
                elif item.get('type') == 'tool_use':
                    tool_name = item.get('name', 'Unknown')
                    tool_input = item.get('input', {})
                    if tool_name == 'Bash':
                        cmd = tool_input.get('command', '')[:200]
                        texts.append(f"[TOOL:Bash] {cmd}")
                    elif tool_name == 'Task':
                        desc = tool_input.get('description', '')
                        agent = tool_input.get('subagent_type', '')
                        texts.append(f"[TOOL:Task] {desc} - subagent: {agent}")
                    elif tool_name in ('Read', 'Write', 'Edit'):
                        path = tool_input.get('file_path', '')
                        texts.append(f"[TOOL:{tool_name}] {path}")
                    else:
                        texts.append(f"[TOOL:{tool_name}]")
        return '\n'.join(texts)
    return str(content)[:500]

def format_message(role, content, max_line_len=200):
    """Format a message into output lines."""
    output = []
    lines = content.split('\n')
    for line in lines:
        if line.strip():
            prefix = f"[{role}]" if role in ('USER', 'ASSISTANT') else ""
            if prefix:
                output.append(f"{prefix} {line[:max_line_len]}")
            else:
                output.append(f"  {line[:max_line_len]}")
    return output

# Parse session
messages = []
session_info = {}

try:
    with open(session_file, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)

                if 'sessionId' in data:
                    session_info['id'] = data['sessionId']
                if 'cwd' in data:
                    session_info['cwd'] = data['cwd']
                if 'timestamp' in data:
                    session_info['timestamp'] = data['timestamp']

                if 'message' in data:
                    msg = data['message']
                    role = msg.get('role', '').upper()
                    content = extract_text(msg.get('content', ''))

                    if role and content:
                        messages.append((role, content))

            except json.JSONDecodeError:
                continue
except Exception as e:
    print(f"Error reading session: {e}", file=sys.stderr)
    sys.exit(1)

# Output header
print("=" * 80)
print(f"SESSION: {session_info.get('id', 'unknown')}")
if session_info.get('timestamp'):
    try:
        ts = datetime.fromisoformat(session_info['timestamp'].replace('Z', '+00:00'))
        print(f"DATE: {ts.strftime('%Y-%m-%d %H:%M')}")
    except:
        pass
print(f"PROJECT: {session_info.get('cwd', 'unknown')}")
if query:
    print(f"FILTER: {query}")
if context_lines > 0:
    print(f"CONTEXT: {context_lines} messages")
if tail_lines > 0:
    print(f"TAIL: {tail_lines} lines")
print("=" * 80)
print()

# Build output lines based on mode
output_lines = []

if query and context_lines > 0:
    # Context mode: find matching messages, include N messages before/after
    match_indices = set()
    for i, (role, content) in enumerate(messages):
        if query in content.lower():
            for j in range(max(0, i - context_lines), min(len(messages), i + context_lines + 1)):
                match_indices.add(j)

    if not match_indices:
        output_lines.append(f"No messages matching '{query}'")
    else:
        sorted_indices = sorted(match_indices)
        # Group consecutive indices into blocks
        blocks = []
        current_block = [sorted_indices[0]]
        for idx in sorted_indices[1:]:
            if idx == current_block[-1] + 1:
                current_block.append(idx)
            else:
                blocks.append(current_block)
                current_block = [idx]
        blocks.append(current_block)

        for block_num, block in enumerate(blocks):
            if block_num > 0:
                output_lines.append("---")
            for idx in block:
                role, content = messages[idx]
                is_match = query in content.lower()
                marker = ">>>" if is_match else "   "
                for line in format_message(role, content):
                    output_lines.append(f"{marker} {line}")

elif query:
    # Filter mode (no context): only show matching messages
    for role, content in messages:
        if query not in content.lower():
            continue
        output_lines.extend(format_message(role, content))
else:
    # No filter: show all messages
    for role, content in messages:
        output_lines.extend(format_message(role, content))

# Apply --tail: keep only last N lines
if tail_lines > 0 and len(output_lines) > tail_lines:
    skipped = len(output_lines) - tail_lines
    output_lines = [f"... (skipped {skipped} lines, showing last {tail_lines})"] + output_lines[-tail_lines:]

# Apply --max-lines: truncate from front
if max_lines > 0 and len(output_lines) > max_lines:
    output_lines = output_lines[:max_lines]
    output_lines.append(f"\n... (truncated at {max_lines} lines)")

# Print output
for line in output_lines:
    print(line)

print()
print("=" * 80)
PYTHON_SCRIPT
}

# ==============================================================================
# MODE 1: Direct extraction (--extract <session-id>)
# ==============================================================================
if [[ -n "$EXTRACT_SESSION" ]]; then
    echo "Extracting session: $EXTRACT_SESSION"
    echo ""

    # Capture stderr for ambiguity messages
    ambiguity_msg=$(mktemp)
    session_file=$(find_session_file "$EXTRACT_SESSION" 2>"$ambiguity_msg")
    find_status=$?

    if [[ -z "$session_file" ]]; then
        echo "Error: Session not found: $EXTRACT_SESSION"
        echo "Searched in: $PROJECT_HISTORY_DIR"
        echo "Also searched all projects in: $CLAUDE_PROJECTS_BASE"
        rm -f "$ambiguity_msg"
        exit 1
    fi

    if [[ $find_status -eq 2 ]]; then
        echo "Warning: Multiple sessions match partial ID '$EXTRACT_SESSION':"
        cat "$ambiguity_msg"
        echo ""
        resolved_id=$(basename "$session_file" .jsonl)
        echo "Using first match: $resolved_id"
        echo "Tip: Provide more characters of the UUID to get an exact match."
        echo ""
    fi
    rm -f "$ambiguity_msg"

    # Show resolved ID if it differs from input (partial match)
    resolved_id=$(basename "$session_file" .jsonl)
    if [[ "$resolved_id" != "$EXTRACT_SESSION" ]]; then
        echo "Resolved partial ID to: $resolved_id"
        echo ""
    fi

    extract_session "$session_file" "$MAX_LINES" "$QUERY"
    exit 0
fi

# ==============================================================================
# MODE 2: Search (with optional extraction)
# ==============================================================================

# Check if project history directory exists
if [[ ! -d "$PROJECT_HISTORY_DIR" ]]; then
    echo "Error: No chat history found for this project"
    echo "Looking for: $PROJECT_HISTORY_DIR"
    echo ""
    echo "Available project histories:"
    ls "$CLAUDE_PROJECTS_BASE" 2>/dev/null | grep -E "^-Users-" | head -10
    exit 1
fi

echo "Query: $QUERY"
echo "Searching in: $PROJECT_HISTORY_DIR"
echo ""

# Find all session files (UUIDs only, not agent files)
while read -r session_file; do
    filename=$(basename "$session_file" .jsonl)

    # Skip if not a UUID format (8-4-4-4-12)
    if [[ ! "$filename" =~ ^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$ ]]; then
        continue
    fi

    # Count matches directly on file (case-insensitive)
    count=$(grep -ci "$QUERY" "$session_file" 2>/dev/null || true)

    # Only include if we have matches
    if [[ -n "$count" ]] && [[ "$count" -gt 0 ]]; then
        mod_time=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$session_file" 2>/dev/null || date -r "$session_file" "+%Y-%m-%d %H:%M" 2>/dev/null || echo "unknown")
        echo "$count|$filename|$mod_time" >> "$RESULTS_FILE"
    fi
done < <(find "$PROJECT_HISTORY_DIR" -maxdepth 1 -name "*.jsonl" -type f ! -name "agent-*")

# Check if we have any results
if [[ ! -s "$RESULTS_FILE" ]]; then
    echo "No matches found for '$QUERY'"
    exit 0
fi

# Sort by match count (descending)
SORTED_RESULTS=$(sort -t'|' -k1 -rn "$RESULTS_FILE")
total_sessions=$(echo "$SORTED_RESULTS" | wc -l | tr -d ' ')
echo "Found $total_sessions session(s) with matches:"
echo ""

# Display search results
count=0
echo "$SORTED_RESULTS" | head -n "$LIMIT" | while IFS='|' read -r matches session_id mod_time; do
    ((count++)) || true
    echo "$count. [${session_id:0:8}] - $matches matches - $mod_time"
    echo "   Full ID: $session_id"
    echo "   Resume: claude --resume $session_id"
    echo ""
done

# ==============================================================================
# MODE 2b: Extract matches if requested
# ==============================================================================
if [[ "$EXTRACT_MATCHES" == true ]]; then
    echo "========================================"
    echo "EXTRACTING TOP $EXTRACT_LIMIT MATCHES"
    echo "========================================"
    echo ""

    extract_count=0
    echo "$SORTED_RESULTS" | head -n "$EXTRACT_LIMIT" | while IFS='|' read -r matches session_id mod_time; do
        ((extract_count++)) || true

        session_file=$(find_session_file "$session_id")
        if [[ -n "$session_file" ]]; then
            echo "[$extract_count/$EXTRACT_LIMIT] Extracting: $session_id"
            extract_session "$session_file" "$MAX_LINES" "$QUERY"
            echo ""
        fi
    done
fi

echo "Tip: Use 'claude --resume <session-id>' to resume a session"
echo "Tip: Use '--extract <id>' to extract a specific session"
echo "Tip: Use '--extract-matches' to auto-extract search results"

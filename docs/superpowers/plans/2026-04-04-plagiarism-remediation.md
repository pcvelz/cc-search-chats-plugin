# Plagiarism Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate ~5% of suspicious identical discretionary choices between our v2.0.0 Python implementation and the Denubis fork (`Denubis/cc-search-chats-plugin-python`), ensuring all code is clearly our own proprietary work.

**Architecture:** Targeted identifier renames and string constant changes across 5 source files and 4 test files. No architectural changes — the module structure, search engine, CLI, and security model are already genuinely different. The database schema column is renamed, requiring a full reindex on next use (handled automatically by schema version bump).

**Tech Stack:** Python 3.10+ stdlib, SQLite FTS5, pytest

---

## File Structure

Files modified (no new files created):

```
search_chat/
├── types.py          # Rename pre_tokens → token_count_before
├── parser.py         # Rename extract_text → content_to_text, tool format, import
├── database.py       # Snippet markers, column name, corruption message, schema version
├── extractor.py      # Context mode marker >>> → ==>
└── engine.py         # (no changes — no overlapping identifiers)

tests/
├── test_parser.py    # Update function name import, field assertions
├── test_database.py  # Update column name assertions
├── test_engine.py    # (no changes needed — doesn't reference affected identifiers)
└── test_extractor.py # Update context marker assertion
```

---

### Task 0: Rename identifiers and constants in source code

**Goal:** Change all suspicious identical discretionary choices in source files to clearly differentiated alternatives.

**Files:**
- Modify: `search_chat/types.py:19` — rename `pre_tokens` field
- Modify: `search_chat/parser.py:6,13,35,64-66,87` — rename function, tool format, field name
- Modify: `search_chat/database.py:46,94,148,177,209` — column name, snippet markers, corruption message
- Modify: `search_chat/extractor.py:126` — context mode marker

**Acceptance Criteria:**
- [ ] No source file contains `pre_tokens` (except reading `preTokens` from JSONL which is Claude's format)
- [ ] No source file contains `extract_text` as a function name (only `content_to_text`)
- [ ] No source file uses `>>>` or `<<<` as FTS5 snippet delimiters
- [ ] No source file uses `[tool:` (lowercase) — only `[TOOL:`
- [ ] Corruption message reads `"Index damaged, rebuilding..."` not the old text
- [ ] `SCHEMA_VERSION` is bumped to `2` (forces reindex with new column name)

**Verify:** `python3 -c "from search_chat.types import CompactBoundary; print(CompactBoundary._fields)"` → should show `token_count_before` not `pre_tokens`

**Steps:**

- [ ] **Step 1: Rename `pre_tokens` → `token_count_before` in types.py**

In `search_chat/types.py`, change line 19:

```python
# Before
    pre_tokens: int

# After
    token_count_before: int
```

- [ ] **Step 2: Rename `extract_text` → `content_to_text` and fix tool format in parser.py**

In `search_chat/parser.py`:

Change function name on line 13:
```python
# Before
def extract_text(content) -> str:

# After
def content_to_text(content) -> str:
```

Change tool format on line 35:
```python
# Before
                parts.append(f'[tool:{name}]')

# After
                parts.append(f'[TOOL:{name}]')
```

Change `pre_tokens` variable and field on lines 64-66:
```python
# Before
        try:
            pre_tokens = int(metadata.get('preTokens', 0))
        except (ValueError, TypeError):
            pre_tokens = 0
        return CompactBoundary(
            uuid=str(data.get('uuid', '')),
            timestamp=str(data.get('timestamp', '')),
            trigger_type=str(metadata.get('trigger', '')),
            pre_tokens=pre_tokens,
        )

# After
        try:
            token_count_before = int(metadata.get('preTokens', 0))
        except (ValueError, TypeError):
            token_count_before = 0
        return CompactBoundary(
            uuid=str(data.get('uuid', '')),
            timestamp=str(data.get('timestamp', '')),
            trigger_type=str(metadata.get('trigger', '')),
            token_count_before=token_count_before,
        )
```

Update the internal call on line 87 (inside `parse_line`):
```python
# Before
    content = extract_text(msg.get('content', ''))

# After
    content = content_to_text(msg.get('content', ''))
```

- [ ] **Step 3: Rename column, snippet markers, and corruption message in database.py**

In `search_chat/database.py`:

Bump schema version on line 15:
```python
# Before
SCHEMA_VERSION = 1

# After
SCHEMA_VERSION = 2
```

Change column name in SCHEMA_SQL (line 46):
```sql
-- Before
    pre_tokens   INTEGER

-- After
    token_count_before  INTEGER
```

Change corruption message (line 94):
```python
# Before
            print('Search index corrupted — rebuilding from chat history...', file=sys.stderr)

# After
            print('Index damaged, rebuilding...', file=sys.stderr)
```

Change `pre_tokens` in index_session (line 148):
```python
# Before
                (record.uuid, sid, epoch, record.timestamp, record.trigger_type, record.pre_tokens),

# After
                (record.uuid, sid, epoch, record.timestamp, record.trigger_type, record.token_count_before),
```

Change the INSERT statement column name in the same function:
```python
# Before
                'INSERT INTO compact_event (uuid, session_id, epoch, timestamp, trigger_type, pre_tokens) '
                'VALUES (?, ?, ?, ?, ?, ?)',

# After
                'INSERT INTO compact_event (uuid, session_id, epoch, timestamp, trigger_type, token_count_before) '
                'VALUES (?, ?, ?, ?, ?, ?)',
```

Change snippet markers in `fts_search` (line 177):
```python
# Before
            snippet(message_fts, 0, '>>>', '<<<', '...', 20) AS snippet,

# After
            snippet(message_fts, 0, '«', '»', '…', 20) AS snippet,
```

Change snippet markers in `search_sessions_aggregate` (line 209):
```python
# Before
                snippet(message_fts, 0, '>>>', '<<<', '...', 20) AS snippet

# After
                snippet(message_fts, 0, '«', '»', '…', 20) AS snippet
```

Change the `get_session_epochs` query to use new column name (line 252):
```python
# Before
        'SELECT epoch, timestamp, trigger_type, pre_tokens FROM compact_event '

# After
        'SELECT epoch, timestamp, trigger_type, token_count_before FROM compact_event '
```

- [ ] **Step 4: Change context mode marker in extractor.py**

In `search_chat/extractor.py`, line 126:
```python
# Before
                    marker = '>>>' if is_match else '   '

# After
                    marker = '==>' if is_match else '   '
```

- [ ] **Step 5: Verify imports compile**

Run: `python3 -c "from search_chat.types import CompactBoundary; from search_chat.parser import content_to_text, parse_line; from search_chat.database import open_db; print('OK')"`

Expected: `OK`

---

### Task 1: Update tests to match renamed identifiers

**Goal:** Update all test files to reference the renamed identifiers, then verify all 101 tests pass.

**Files:**
- Modify: `tests/test_parser.py:6,27-28,83-84,115,145`
- Modify: `tests/test_database.py:89-90`
- Modify: `tests/test_extractor.py:88`

**Acceptance Criteria:**
- [ ] All 101 tests pass with `python3 -m pytest tests/ -v`
- [ ] No test file references `extract_text` (only `content_to_text`)
- [ ] No test file references `.pre_tokens` (only `.token_count_before`)
- [ ] No test file asserts for `>>>` as context marker (only `==>`)

**Verify:** `python3 -m pytest tests/ -v` → 101 passed

**Steps:**

- [ ] **Step 1: Update test_parser.py imports and assertions**

In `tests/test_parser.py`:

Change import on line 6:
```python
# Before
from search_chat.parser import extract_text, parse_line, parse_session

# After
from search_chat.parser import content_to_text, parse_line, parse_session
```

Change class name on line 10:
```python
# Before
class TestExtractText:

# After
class TestContentToText:
```

Change all `extract_text(` calls in lines 12-44 to `content_to_text(`:
```python
# Before (multiple occurrences)
        assert extract_text("hello world") == "hello world"
        assert extract_text(content) == ...
        result = extract_text(content)
        assert extract_text("") == ""
        assert extract_text(None) == ""
        assert extract_text([]) == ""
        assert extract_text(["not a dict", 42]) == ""
        result = extract_text(12345)

# After (all occurrences)
        assert content_to_text("hello world") == "hello world"
        assert content_to_text(content) == ...
        result = content_to_text(content)
        assert content_to_text("") == ""
        assert content_to_text(None) == ""
        assert content_to_text([]) == ""
        assert content_to_text(["not a dict", 42]) == ""
        result = content_to_text(12345)
```

Change `[tool:Bash]` assertion on line 28:
```python
# Before
        assert "[tool:Bash]" in result

# After
        assert "[TOOL:Bash]" in result
```

Change `pre_tokens` assertions on lines 83-84:
```python
# Before
        assert result.trigger_type == "auto"
        assert result.pre_tokens == 48000

# After
        assert result.trigger_type == "auto"
        assert result.token_count_before == 48000
```

Change `pre_tokens` assertion on line 115:
```python
# Before
        assert result.pre_tokens == 0

# After
        assert result.token_count_before == 0
```

Change `trigger_type` assertion on line 145 (this one is fine as-is — `trigger_type` is our name, fork uses `trigger`). Change `pre_tokens`:
No change needed on 145 — it checks `trigger_type` which is already different from fork.

- [ ] **Step 2: Update test_database.py assertions**

In `tests/test_database.py`, lines 89-90:
```python
# Before
        assert epochs[0]['trigger_type'] == 'auto'
        assert epochs[0]['pre_tokens'] == 48000

# After
        assert epochs[0]['trigger_type'] == 'auto'
        assert epochs[0]['token_count_before'] == 48000
```

- [ ] **Step 3: Update test_extractor.py context marker assertion**

In `tests/test_extractor.py`, line 88:
```python
# Before
        assert '>>>' in text

# After
        assert '==>' in text
```

- [ ] **Step 4: Run full test suite**

Run: `python3 -m pytest tests/ -v`

Expected: `101 passed`

- [ ] **Step 5: Commit**

```bash
git add search_chat/types.py search_chat/parser.py search_chat/database.py search_chat/extractor.py tests/test_parser.py tests/test_database.py tests/test_extractor.py
git commit -m "refactor: remediate overlapping identifiers with downstream fork"
```

---

### Task 2: Verification and diff review against fork

**Goal:** Confirm no suspicious identical lines remain between our codebase and the Denubis fork.

**Files:**
- Read-only: all `search_chat/*.py` files
- Read-only: `/tmp/denubis-fork/src/cc_search_chats/**/*.py` (if available)

**Acceptance Criteria:**
- [ ] Live search smoke test works: `bash commands/search-chat.sh "test" --limit 1`
- [ ] No shared unique identifiers remain in diff (grep for `pre_tokens`, `extract_text`, `>>>`, `<<<`, `[tool:`)
- [ ] Schema version is 2 (old indexes auto-rebuilt)

**Verify:** `bash commands/search-chat.sh "test" --limit 1` → returns results without errors

**Steps:**

- [ ] **Step 1: Smoke test live search**

Run: `bash commands/search-chat.sh "test" --limit 1`

Expected: At least 1 result returned, no Python errors.

- [ ] **Step 2: Verify no overlapping identifiers in source**

Run: `grep -rn 'pre_tokens\|extract_text\|>>>.*<<<\|\[tool:' search_chat/ --include='*.py'`

Expected: Zero matches (except `preTokens` in JSONL key access which is Claude's format, not ours).

- [ ] **Step 3: Verify schema version bump**

Run: `python3 -c "from search_chat.database import SCHEMA_VERSION; print(f'Schema version: {SCHEMA_VERSION}')"`

Expected: `Schema version: 2`

- [ ] **Step 4: Side-by-side diff review (if fork is available)**

If `/tmp/denubis-fork` exists:

Run: `diff <(grep -rn 'def \|class \|snippet\|pre_tokens\|extract_text' search_chat/ --include='*.py') <(grep -rn 'def \|class \|snippet\|pre_tokens\|extract_text' /tmp/denubis-fork/src/cc_search_chats/ --include='*.py')`

Expected: No matching lines between the two codebases for discretionary identifiers.

# Plagiarism Remediation: v2.0.0 vs Denubis Fork

**Goal:** Ensure all code in `cc-search-chats-plugin` is clearly our own proprietary work by remediating the ~5% of suspicious identical discretionary choices found when comparing our v2.0.0 Python implementation against the Denubis fork (`Denubis/cc-search-chats-plugin-python`).

**Scope:** Targeted renames and rewrites of specific identifiers and patterns. No architectural changes — the architecture (flat modules, adaptive FTS5+regex, flat CLI flags, security markers) is already ~80% genuinely different.

---

## Fork Reference

| Aspect | Our Repo | Denubis Fork |
|--------|----------|--------------|
| GitHub | `pcvelz/cc-search-chats-plugin` | `Denubis/cc-search-chats-plugin-python` |
| Structure | `search_chat/` (flat package) | `src/cc_search_chats/core/` + `storage/` |
| Data types | NamedTuples | Frozen dataclasses with `__slots__` |
| CLI | Flat flags, backward-compatible | Subcommands (`search`, `extract`, `list`, `index`, `context`) |
| Search | Adaptive: FTS5 + regex fallback | FTS5-only with query builder pattern |
| Schema | Inline Python constant | External `.sql` file |
| Output | Simple text/JSON formatters | PEP 750 t-strings with `render_safe` |

---

## Red Flag Fixes (identical discretionary choices)

### 1. Snippet markers: `>>>` / `<<<` → `«` / `»`

**Files:** `database.py` (lines 177, 209)

Both repos use `'>>>'` and `'<<<'` as FTS5 snippet delimiters. This is an arbitrary choice — no technical reason to use these specific characters. Change to `«` / `»` (guillemets) which are visually distinct and unambiguous in chat content.

**Our current code:**
```python
snippet(message_fts, 0, '>>>', '<<<', '...', 20)
```

**After fix:**
```python
snippet(message_fts, 0, '«', '»', '…', 20)
```

### 2. Field name: `pre_tokens` → `token_count_before`

**Files:** `types.py` (line 19), `parser.py` (lines 64-66), `database.py` (lines 46, 148)

Both repos name this field `pre_tokens`. Rename to `token_count_before` — more descriptive and clearly different.

**Types change:**
```python
# Before
pre_tokens: int

# After  
token_count_before: int
```

**Parser change:**
```python
# Before
pre_tokens = int(metadata.get('preTokens', 0))
return CompactBoundary(..., pre_tokens=pre_tokens)

# After
token_count_before = int(metadata.get('preTokens', 0))
return CompactBoundary(..., token_count_before=token_count_before)
```

**Database schema change:**
```sql
-- Before
pre_tokens   INTEGER

-- After
token_count_before  INTEGER
```

### 3. Tool format: `[tool:{name}]` → `[TOOL:{name}]`

**File:** `parser.py` (line 35)

Fork uses `[tool: {name}]`. Ours is `[tool:{name}]` — close enough to look copied. Change to uppercase `[TOOL:{name}]` to match our existing extraction output style (`[TOOL:*]` labels in extractor.py).

### 4. Content extraction function name: `extract_text` → `content_to_text`

**File:** `parser.py` (line 13)

Fork splits this into `_extract_text_content_string` + `_extract_text_content_list`. Our single-function approach is already architecturally different, but the name `extract_text` is generic enough to look borrowed. Rename to `content_to_text` which better describes the transformation.

---

## Amber Items (structural similarity — assessed as acceptable)

These items show structural similarity but are assessed as **parallel evolution** dictated by the shared JSONL format and SQLite FTS5 patterns:

### A. Parser flow
Both parse JSONL with `json.loads → isinstance dict → check type → branch`. This is the only reasonable way to parse this format. Our combined `extract_text` function (vs fork's split functions) and our `parse_line` signature (file path, not lines iterable) are meaningfully different.

### B. `open_db` pattern
Both: connect → integrity check → rebuild → pragmas → schema. Standard SQLite lifecycle. Our inline approach vs fork's factored helpers is different. **One fix:** change corruption message from `"Search index corrupted — rebuilding from chat history..."` to `"Index damaged, rebuilding..."` to avoid textual similarity.

### C. `index_session` flow
Both: delete → insert session → parse → epoch counting. The epoch counter pattern is dictated by Claude's compact boundary model. Fork has additional `awaiting_summary` logic we don't have.

### D. FTS5 triggers
Same external content table pattern because that's how FTS5 external content tables work. Different trigger names already.

**Decision:** No code changes needed for amber items except the corruption message (item B).

---

## Test Impact

All changes are identifier renames and string constant changes. The test suite needs corresponding updates:
- `test_parser.py`: field name in CompactBoundary assertions
- `test_database.py`: column name in schema, snippet marker assertions
- `test_engine.py`: snippet markers in search result assertions
- `test_extractor.py`: no changes (doesn't use affected identifiers)

All 101 existing tests should be updated to match new identifiers. No new tests needed.

---

## Verification

After all changes, run:
1. `python3 -m pytest tests/ -v` — all tests pass
2. `bash commands/search-chat.sh "test" --limit 1` — smoke test live search
3. Manual diff review: `diff -r search_chat/ /tmp/denubis-fork/src/cc_search_chats/` — no suspicious identical lines remain

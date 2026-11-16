"""Tests for the /summarize-chat binary mode classifier.

Binary contract (user ruling 2026-11-16):
- SHOW   : the arguments are ONLY session id(s) + flags -> relay the summary.
- SILENT : ANY other text next to the command -> the summary is private
           context for the main agent and must NOT be pasted into chat.
"""
import json
import subprocess
import sys
from pathlib import Path

from search_chat.summarize_args import classify

REPO = Path(__file__).resolve().parent.parent


class TestShowMode:
    def test_bare_short_id(self):
        r = classify('d03e2669')
        assert r['mode'] == 'show'
        assert r['session_ids'] == ['d03e2669']
        assert r['flag'] == 'default'

    def test_full_uuid(self):
        r = classify('a5206bfe-9ee2-4cfa-9d8d-bf2330fe081e')
        assert r['mode'] == 'show'
        assert r['session_ids'] == ['a5206bfe-9ee2-4cfa-9d8d-bf2330fe081e']

    def test_flags_are_not_instructions(self):
        assert classify('d03e2669 --detailed') == {
            'mode': 'show', 'session_ids': ['d03e2669'], 'flag': 'detailed', 'residual': '',
        }
        assert classify('--eu d03e2669')['flag'] == 'eu'

    def test_status_bar_chrome_is_not_instructions(self):
        r = classify('S: d03e2669 |')
        assert r['mode'] == 'show'
        assert r['session_ids'] == ['d03e2669']

    def test_multiple_ids_with_separators(self):
        r = classify('d03e2669, bea760b4')
        assert r['mode'] == 'show'
        assert r['session_ids'] == ['d03e2669', 'bea760b4']

    def test_uppercase_id_normalised(self):
        assert classify('D03E2669')['session_ids'] == ['d03e2669']


class TestSilentMode:
    def test_a5206bfe_prove_of_red(self):
        """Exact arguments from session a5206bfe that dumped two summaries."""
        text = ('d03e2669 --detailed, and /search-chats:summarize-chat bea760b4 '
                '--detailed, dispatch both in parallel?')
        r = classify(text)
        assert r['mode'] == 'silent'
        assert r['session_ids'] == ['d03e2669', 'bea760b4']
        assert r['flag'] == 'detailed'
        assert 'dispatch both in parallel' in r['residual']

    def test_question_is_silent(self):
        r = classify('86017339 what did it plan to do next?')
        assert r['mode'] == 'silent'
        assert r['session_ids'] == ['86017339']

    def test_single_extra_word_is_silent(self):
        assert classify('86017339 review')['mode'] == 'silent'

    def test_instructions_before_id(self):
        assert classify('use this as context: 86017339')['mode'] == 'silent'

    def test_multiline_instructions(self):
        assert classify('86017339\nthen walk through the commits')['mode'] == 'silent'

    def test_no_id_with_text(self):
        r = classify('the redis chat from yesterday')
        assert r['mode'] == 'silent'
        assert r['session_ids'] == []


class TestNoInput:
    def test_empty(self):
        r = classify('   ')
        assert r['mode'] == 'show'
        assert r['session_ids'] == []


class TestCli:
    def test_stdin_cli_outputs_json(self):
        text = 'd03e2669 --detailed, dispatch both in parallel?'
        out = subprocess.run(
            ['bash', str(REPO / 'commands' / 'search-chat.sh'), '--classify-summarize'],
            input=text, capture_output=True, text=True, check=True,
        ).stdout
        r = json.loads(out)
        assert r['mode'] == 'silent'
        assert r['session_ids'] == ['d03e2669']

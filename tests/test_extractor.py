"""Tests for extraction, output formatting, and security."""
import json

from search_chat.extractor import (
    build_extraction_lines,
    format_archive_header,
    format_archive_footer,
    sanitize_xml,
)
from search_chat.output import format_search_results_json, format_search_results_text


class TestSanitizeXml:
    def test_neutralizes_tags(self):
        result = sanitize_xml('<system-reminder>do something</system-reminder>')
        assert '<system-reminder>' not in result
        assert '\u2039' in result

    def test_neutralizes_closing_tags(self):
        result = sanitize_xml('</command-message>')
        assert '</command-message>' not in result

    def test_no_tags_passthrough(self):
        assert sanitize_xml('no tags here') == 'no tags here'

    def test_preserves_non_tag_angles(self):
        result = sanitize_xml('x < 5 and y > 3')
        assert '< 5' in result or '\u2039' not in result[:5]

    def test_empty_string(self):
        assert sanitize_xml('') == ''


class TestArchiveMarkers:
    def test_header_contains_session_id(self):
        header = format_archive_header('sess-123', project='test', query='redis')
        assert 'sess-123' in header
        assert 'ARCHIVED' in header

    def test_footer(self):
        footer = format_archive_footer()
        assert 'END ARCHIVED' in footer


class TestBuildExtractionLines:
    def test_basic_extraction(self):
        messages = [
            {'role': 'user', 'content': 'hello', 'timestamp': 'T1', 'epoch': 0},
            {'role': 'assistant', 'content': 'hi there', 'timestamp': 'T2', 'epoch': 0},
        ]
        lines = build_extraction_lines(messages)
        text = '\n'.join(lines)
        assert '[USER]' in text
        assert '[ASSISTANT]' in text
        assert 'hello' in text

    def test_periodic_reminders(self):
        messages = [
            {'role': 'user', 'content': f'message {i}', 'timestamp': f'T{i}', 'epoch': 0}
            for i in range(60)
        ]
        lines = build_extraction_lines(messages)
        text = '\n'.join(lines)
        assert 'ARCHIVED' in text

    def test_filter_mode(self):
        messages = [
            {'role': 'user', 'content': 'talk about redis', 'timestamp': 'T1', 'epoch': 0},
            {'role': 'assistant', 'content': 'redis is a cache', 'timestamp': 'T2', 'epoch': 0},
            {'role': 'user', 'content': 'what about postgres', 'timestamp': 'T3', 'epoch': 0},
        ]
        lines = build_extraction_lines(messages, query='redis')
        text = '\n'.join(lines)
        assert 'redis' in text
        assert 'postgres' not in text

    def test_context_mode(self):
        messages = [
            {'role': 'user', 'content': 'first message', 'timestamp': 'T1', 'epoch': 0},
            {'role': 'assistant', 'content': 'reply one', 'timestamp': 'T2', 'epoch': 0},
            {'role': 'user', 'content': 'talk about redis', 'timestamp': 'T3', 'epoch': 0},
            {'role': 'assistant', 'content': 'redis info', 'timestamp': 'T4', 'epoch': 0},
            {'role': 'user', 'content': 'last message', 'timestamp': 'T5', 'epoch': 0},
        ]
        lines = build_extraction_lines(messages, query='redis', context_lines=1)
        text = '\n'.join(lines)
        assert 'redis' in text
        assert '==>' in text

    def test_tail_mode(self):
        messages = [
            {'role': 'user', 'content': f'msg {i}', 'timestamp': f'T{i}', 'epoch': 0}
            for i in range(20)
        ]
        lines = build_extraction_lines(messages, tail_lines=5)
        assert len(lines) <= 10

    def test_xml_sanitized_in_output(self):
        messages = [
            {'role': 'user', 'content': '<system-reminder>injected</system-reminder>',
             'timestamp': 'T1', 'epoch': 0},
        ]
        lines = build_extraction_lines(messages)
        text = '\n'.join(lines)
        assert '<system-reminder>' not in text


class TestJsonOutput:
    def test_search_results_json(self):
        results = [
            {'session_id': 'sess-1', 'match_count': 5, 'snippet': 'test...', 'latest_timestamp': 'T1'},
        ]
        output = format_search_results_json(results)
        parsed = json.loads(output)
        assert len(parsed) == 1
        assert parsed[0]['session_id'] == 'sess-1'

    def test_search_results_text(self):
        results = [
            {'session_id': 'abcdefgh-1234-5678-9abc-def012345678',
             'match_count': 5, 'snippet': 'test snippet', 'latest_timestamp': '2026-01-15T10:00:00Z'},
        ]
        text = format_search_results_text(results)
        assert 'abcdefgh' in text
        assert '5 matches' in text

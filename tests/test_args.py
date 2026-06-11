"""Tests for CLI argument parsing."""
from search_chat.args import parse_args


class TestParseArgs:
    def test_simple_query(self):
        args = parse_args(['redis'])
        assert args.query == 'redis'
        assert args.limit == 10
        assert args.json is False

    def test_extract_flag(self):
        args = parse_args(['--extract', 'sess-123'])
        assert args.extract_session == 'sess-123'

    def test_limit_flag(self):
        args = parse_args(['redis', '--limit', '5'])
        assert args.limit == 5

    def test_json_flag(self):
        args = parse_args(['redis', '--json'])
        assert args.json is True

    def test_extract_matches(self):
        args = parse_args(['redis', '--extract-matches'])
        assert args.extract_matches is True

    def test_context_flag(self):
        args = parse_args(['redis', '--context', '3'])
        assert args.context_lines == 3

    def test_tail_flag(self):
        args = parse_args(['redis', '--tail', '50'])
        assert args.tail_lines == 50

    def test_all_projects(self):
        args = parse_args(['redis', '--all-projects'])
        assert args.all_projects is True

    def test_include_agents(self):
        args = parse_args(['redis', '--include-agents'])
        assert args.include_agents is True

    def test_include_self(self):
        args = parse_args(['redis', '--include-self'])
        assert args.include_self is True

    def test_exclude_session(self):
        args = parse_args(['redis', '--exclude-session', 'sess-999'])
        assert args.exclude_session == 'sess-999'

    def test_project_flag(self):
        args = parse_args(['redis', '--project', '/path/to/proj'])
        assert args.project_path == '/path/to/proj'

    def test_uuid_auto_detection_full(self):
        args = parse_args(['abcdef01-2345-6789-abcd-ef0123456789'])
        assert args.extract_session == 'abcdef01-2345-6789-abcd-ef0123456789'
        assert args.query == ''

    def test_uuid_with_filter_text(self):
        args = parse_args(['abcdef01-2345-6789-abcd-ef0123456789', 'redis', 'cache'])
        assert args.extract_session == 'abcdef01-2345-6789-abcd-ef0123456789'
        assert args.query == 'redis cache'

    def test_uuid_with_embedded_flags(self):
        args = parse_args(['abcdef01-2345-6789-abcd-ef0123456789', '--tail', '30'])
        assert args.extract_session == 'abcdef01-2345-6789-abcd-ef0123456789'
        assert args.tail_lines == 30

    def test_short_uuid_detection(self):
        args = parse_args(['abcdef01'])
        assert args.extract_session == 'abcdef01'

    def test_max_lines(self):
        args = parse_args(['--extract', 'sess-1', '--max-lines', '200'])
        assert args.max_lines == 200

    def test_multi_word_query(self):
        args = parse_args(['deploy', 'to', 'staging'])
        assert args.query == 'deploy to staging'

    def test_help_flag(self):
        import pytest
        with pytest.raises(SystemExit) as exc_info:
            parse_args(['--help'])
        assert exc_info.value.code == 0

    def test_embedded_full_uuid_in_status_bar_text(self):
        args = parse_args(['S: a1b2c3d4-1234-5678-abcd-ef0123456789 | C: [█░░░] 265k/1M | D5/7: On Pace'])
        assert args.extract_session == 'a1b2c3d4-1234-5678-abcd-ef0123456789'
        assert args.query == '265k/1M D5/7 On Pace'
        assert args.tail_lines == 200

    def test_embedded_full_uuid_in_messy_text(self):
        args = parse_args(['Session: a1b2c3d4-1234-5678-abcd-ef0123456789 | done'])
        assert args.extract_session == 'a1b2c3d4-1234-5678-abcd-ef0123456789'
        assert args.query == 'Session done'
        assert args.tail_lines == 200

    def test_embedded_full_uuid_with_remaining_filter_text(self):
        args = parse_args(['S: a1b2c3d4-1234-5678-abcd-ef0123456789 redis cache'])
        assert args.extract_session == 'a1b2c3d4-1234-5678-abcd-ef0123456789'
        assert args.query == 'redis cache'

    def test_no_embedded_short_uuid_scan_in_prose(self):
        # A bare 8-hex token that is NOT the first word must not be auto-detected:
        # the embedded second-chance scan only matches FULL UUIDs, never short hex.
        args = parse_args(['the deadc0de bug in module x'])
        assert args.extract_session == ''
        assert args.query == 'the deadc0de bug in module x'
        assert args.auto_detected_uuid is False

    def test_short_uuid_with_filter_text(self):
        # Documented form (README: `search-chat bbfba5e4 chrome tag`): a short ID
        # as the first token still extracts, with trailing words as the filter.
        args = parse_args(['bbfba5e4', 'chrome', 'tag'])
        assert args.extract_session == 'bbfba5e4'
        assert args.query == 'chrome tag'

    def test_embedded_uuid_does_not_override_explicit_extract(self):
        # Explicit --extract must never be overridden by auto-detection.
        args = parse_args(['--extract', 'sess-123', 'some a1b2c3d4 text'])
        assert args.extract_session == 'sess-123'
        assert args.query == 'some a1b2c3d4 text'

    def test_embedded_full_uuid_with_explicit_tail_flag(self):
        args = parse_args(['S: a1b2c3d4-1234-5678-abcd-ef0123456789 | C: [█░░░] 265k/1M | D5/7: On Pace', '--tail', '200'])
        assert args.extract_session == 'a1b2c3d4-1234-5678-abcd-ef0123456789'
        assert args.tail_lines == 200
        assert args.query == '265k/1M D5/7 On Pace'

    def test_long_follow_up_preserved_after_full_uuid(self):
        # Genuine follow-up words after a UUID must survive chrome-stripping.
        args = parse_args(['Session: a1b2c3d4-1234-5678-abcd-ef0123456789 please summarize the caching discussion we had'])
        assert args.extract_session == 'a1b2c3d4-1234-5678-abcd-ef0123456789'
        assert args.query == 'Session please summarize the caching discussion we had'

    def test_list_flag(self):
        args = parse_args(['--list'])
        assert args.list_mode is True
        assert args.query == ''

    def test_list_with_topic(self):
        args = parse_args(['--list', 'staging', 'deploy'])
        assert args.list_mode is True
        assert args.query == 'staging deploy'

    def test_list_all_projects(self):
        args = parse_args(['--list', 'redis', '--all-projects'])
        assert args.list_mode is True
        assert args.all_projects is True
        assert args.query == 'redis'

    def test_list_does_not_autodetect_uuid(self):
        args = parse_args(['--list', 'abcdef01'])
        assert args.list_mode is True
        assert args.extract_session == ''
        assert args.query == 'abcdef01'

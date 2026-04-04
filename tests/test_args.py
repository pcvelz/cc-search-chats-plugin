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

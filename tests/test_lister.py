"""Tests for the /find-chat candidate-listing core."""
from search_chat.finder import list_session_files
from search_chat.lister import build_list_items, score_session, topic_tokens
from search_chat.types import SessionListItem


class TestTopicTokens:
    def test_drops_stopwords_and_short_tokens(self):
        tokens = topic_tokens("find the last chat where we discussed the staging deploy")
        assert tokens == ["staging", "deploy"]

    def test_empty_when_all_stopwords(self):
        assert topic_tokens("the last one we had") == []

    def test_lowercases_and_splits_punctuation(self):
        assert topic_tokens("Redis-cache, config!") == ["redis", "cache", "config"]


class TestScoreSession:
    def test_counts_distinct_tokens(self, sample_session_path):
        # sample_session opening prompt: "How do I deploy to staging?" + redis turn
        assert score_session(sample_session_path, ["deploy"]) == 1
        assert score_session(sample_session_path, ["deploy", "redis"]) == 2

    def test_zero_when_no_match(self, sample_session_path):
        assert score_session(sample_session_path, ["kuberneteszzz"]) == 0

    def test_empty_tokens_score_zero(self, sample_session_path):
        assert score_session(sample_session_path, []) == 0


class TestBuildListItems:
    def test_no_topic_returns_recency(self, tmp_project):
        import time
        _, project_dir = tmp_project
        (project_dir / "aaaaaaaa-1111-2222-3333-444444444444.jsonl").touch()
        time.sleep(0.01)
        files = list_session_files(project_dir)
        items = build_list_items(files, topic="", limit=3)
        assert len(items) == 2
        assert all(isinstance(it, SessionListItem) for it in items)
        assert items[0].session_id == "aaaaaaaa-1111-2222-3333-444444444444"
        assert items[0].title == "How do I deploy to staging?"

    def test_topic_filters_to_matches(self, tmp_project):
        _, project_dir = tmp_project
        files = list_session_files(project_dir)
        items = build_list_items(files, topic="staging deploy", limit=3)
        ids = {it.session_id for it in items}
        assert "aaaaaaaa-1111-2222-3333-444444444444" in ids

    def test_topic_no_match_returns_empty(self, tmp_project):
        _, project_dir = tmp_project
        files = list_session_files(project_dir)
        assert build_list_items(files, topic="zzzznope", limit=3) == []

    def test_limit_caps_results(self, tmp_project):
        _, project_dir = tmp_project
        files = list_session_files(project_dir)
        assert len(build_list_items(files, topic="", limit=1)) == 1

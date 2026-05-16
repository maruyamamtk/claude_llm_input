"""collect_agent.py のユニットテスト（LLM・チェーン呼び出しをモック）"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from agent.collect_agent import (
    CollectAgent,
    CollectAgentState,
    _EvaluationResult,
)
from models.article import Article


def _make_twitter_article(
    title: str = "AI最新ツイート",
    url: str = "https://x.com/AnthropicAI/status/1",
    summary: str = "ツイート要約",
    is_related: bool = True,
) -> Article:
    return Article(
        title=title,
        url=url,
        source="@AnthropicAI",
        summary=summary,
        is_related=is_related,
        category="twitter",
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_article(
    title: str = "Claude Code の使い方",
    url: str = "https://example.com/article",
    summary: str = "要約テキスト",
    is_related: bool = True,
    category: str = "anthropic",
) -> Article:
    return Article(
        title=title,
        url=url,
        source="test",
        summary=summary,
        is_related=is_related,
        category=category,
    )


def _make_agent() -> CollectAgent:
    """全チェーン・LLMをモックした CollectAgent を返す。"""
    with (
        patch("agent.collect_agent.BlogChain"),
        patch("agent.collect_agent.GithubChain"),
        patch("agent.collect_agent.TwitterChain"),
        patch("agent.collect_agent.FilterChain"),
        patch("agent.collect_agent.SummarizerChain"),
        patch("agent.collect_agent.ReporterChain"),
        patch("agent.collect_agent.ChatGoogleGenerativeAI"),
        patch("agent.collect_agent.ChatPromptTemplate"),
    ):
        agent = CollectAgent.__new__(CollectAgent)
        agent._blog_chain = MagicMock()
        agent._github_chain = MagicMock()
        agent._twitter_chain = MagicMock()
        agent._filter_chain = MagicMock()
        agent._summarizer_chain = MagicMock()
        agent._reporter_chain = MagicMock()
        agent._evaluate_chain = MagicMock()
        agent.graph = agent._build_graph()
    return agent


def _make_state(**kwargs) -> CollectAgentState:
    defaults: CollectAgentState = {
        "run_date": date(2026, 5, 9),
        "raw_articles": [],
        "articles": [],
        "retry_count": 0,
        "evaluation": {},
        "final_report": "",
    }
    defaults.update(kwargs)
    return defaults


# ─── State definitions ────────────────────────────────────────────────────────


class TestStateDefinitions:
    def test_collect_agent_state_fields(self):
        state = _make_state()
        assert "run_date" in state
        assert "raw_articles" in state
        assert "articles" in state
        assert "retry_count" in state
        assert "evaluation" in state
        assert "final_report" in state

    def test_initial_retry_count_is_zero(self):
        state = _make_state()
        assert state["retry_count"] == 0


# ─── collect_blog / collect_github nodes ─────────────────────────────────────


class TestCollectNodes:
    def test_collect_blog_returns_raw_articles(self):
        agent = _make_agent()
        blog_article = _make_article(title="Blog Article", url="https://blog.example.com")
        agent._blog_chain.run.return_value = [blog_article]

        state = _make_state()
        result = agent._collect_blog_node(state)

        assert "raw_articles" in result
        assert len(result["raw_articles"]) == 1
        assert result["raw_articles"][0].title == "Blog Article"

    def test_collect_github_returns_raw_articles(self):
        agent = _make_agent()
        github_article = _make_article(title="GitHub Release", url="https://github.com/repo/v1.0")
        agent._github_chain.run.return_value = [github_article]

        state = _make_state()
        result = agent._collect_github_node(state)

        assert "raw_articles" in result
        assert len(result["raw_articles"]) == 1

    def test_collect_twitter_returns_raw_articles(self):
        agent = _make_agent()
        twitter_article = _make_twitter_article()
        agent._twitter_chain.run.return_value = [twitter_article]

        state = _make_state()
        result = agent._collect_twitter_node(state)

        assert "raw_articles" in result
        assert len(result["raw_articles"]) == 1
        assert result["raw_articles"][0].category == "twitter"

    def test_collect_blog_empty_result(self):
        agent = _make_agent()
        agent._blog_chain.run.return_value = []

        state = _make_state()
        result = agent._collect_blog_node(state)

        assert result["raw_articles"] == []


# ─── filter_and_summarize node ────────────────────────────────────────────────


class TestFilterAndSummarize:
    def test_deduplicates_by_url(self):
        agent = _make_agent()
        dup_url = "https://example.com/dup"
        articles = [
            _make_article(title="A", url=dup_url),
            _make_article(title="B", url=dup_url),
            _make_article(title="C", url="https://example.com/unique"),
        ]
        filtered = [
            articles[0].model_copy(update={"is_related": True}),
            articles[2].model_copy(update={"is_related": True}),
        ]
        agent._filter_chain.run.return_value = filtered
        agent._summarizer_chain.run.side_effect = lambda a: a.model_copy(
            update={"summary": "要約"}
        )

        state = _make_state(raw_articles=articles)
        result = agent._filter_and_summarize_node(state)

        # filter_chain should receive deduplicated (2 unique URLs)
        call_args = agent._filter_chain.run.call_args[0][0]
        urls = [a.url for a in call_args]
        assert len(urls) == len(set(urls))

    def test_only_related_articles_are_summarized(self):
        agent = _make_agent()
        related = _make_article(url="https://example.com/1", is_related=True)
        not_related = _make_article(url="https://example.com/2", is_related=False)
        agent._filter_chain.run.return_value = [related, not_related]
        agent._summarizer_chain.run.side_effect = lambda a: a

        state = _make_state(raw_articles=[related, not_related])
        result = agent._filter_and_summarize_node(state)

        # Summarizer called only for related article
        assert agent._summarizer_chain.run.call_count == 1
        assert len(result["articles"]) == 1

    def test_returns_empty_when_no_related(self):
        agent = _make_agent()
        article = _make_article(is_related=False)
        agent._filter_chain.run.return_value = [article]

        state = _make_state(raw_articles=[article])
        result = agent._filter_and_summarize_node(state)

        assert result["articles"] == []

    def test_empty_raw_articles(self):
        agent = _make_agent()
        agent._filter_chain.run.return_value = []

        state = _make_state(raw_articles=[])
        result = agent._filter_and_summarize_node(state)

        assert result["articles"] == []


# ─── evaluate node ────────────────────────────────────────────────────────────


class TestEvaluateNode:
    def test_increments_retry_count(self):
        agent = _make_agent()
        agent._evaluate_chain.invoke.return_value = _EvaluationResult(
            need_more=False, tip_count=5, reason="十分"
        )
        state = _make_state(retry_count=0)
        result = agent._evaluate_node(state)

        assert result["retry_count"] == 1

    def test_sets_evaluation_need_more_true(self):
        agent = _make_agent()
        agent._evaluate_chain.invoke.return_value = _EvaluationResult(
            need_more=True, tip_count=1, reason="Tipsが少ない"
        )
        state = _make_state()
        result = agent._evaluate_node(state)

        assert result["evaluation"]["need_more"] is True

    def test_sets_evaluation_need_more_false(self):
        agent = _make_agent()
        agent._evaluate_chain.invoke.return_value = _EvaluationResult(
            need_more=False, tip_count=5, reason="十分"
        )
        state = _make_state()
        result = agent._evaluate_node(state)

        assert result["evaluation"]["need_more"] is False

    def test_error_defaults_to_no_retry(self):
        agent = _make_agent()
        agent._evaluate_chain.invoke.side_effect = Exception("API error")
        state = _make_state()
        result = agent._evaluate_node(state)

        assert result["evaluation"]["need_more"] is False

    def test_retry_count_never_exceeds_max(self):
        agent = _make_agent()
        agent._evaluate_chain.invoke.return_value = _EvaluationResult(
            need_more=True, tip_count=1, reason="不足"
        )
        # Simulate 3 rounds of evaluation
        state = _make_state(retry_count=2)
        result = agent._evaluate_node(state)
        assert result["retry_count"] == 3  # Reaches max but does not exceed


# ─── evaluate_routing ─────────────────────────────────────────────────────────


class TestEvaluateRouting:
    def test_routes_to_collect_when_need_more_and_under_limit(self):
        agent = _make_agent()
        state = _make_state(
            evaluation={"need_more": True, "tip_count": 1, "reason": "不足"},
            retry_count=1,  # 1 < max_retry_loops(3)
        )
        assert agent._evaluate_routing(state) == "collect"

    def test_routes_to_report_when_not_need_more(self):
        agent = _make_agent()
        state = _make_state(
            evaluation={"need_more": False, "tip_count": 5, "reason": "十分"},
            retry_count=1,
        )
        assert agent._evaluate_routing(state) == "report"

    def test_routes_to_report_at_retry_limit(self):
        agent = _make_agent()
        # retry_count exceeds max_retry_loops (3): retry_count=4 means 3 retries done
        state = _make_state(
            evaluation={"need_more": True, "tip_count": 1, "reason": "不足"},
            retry_count=4,
        )
        assert agent._evaluate_routing(state) == "report"

    def test_routes_to_collect_at_exact_max_retries(self):
        agent = _make_agent()
        # retry_count == max_retry_loops: still allowed (3rd retry)
        state = _make_state(
            evaluation={"need_more": True, "tip_count": 1, "reason": "不足"},
            retry_count=3,
        )
        assert agent._evaluate_routing(state) == "collect"

    def test_routes_to_report_with_empty_evaluation(self):
        agent = _make_agent()
        state = _make_state(evaluation={})
        assert agent._evaluate_routing(state) == "report"


# ─── generate_report node ─────────────────────────────────────────────────────


class TestGenerateReport:
    def test_calls_reporter_chain_with_articles_and_date(self):
        agent = _make_agent()
        agent._reporter_chain.run.return_value = "# レポート"
        articles = [_make_article()]
        run_date = date(2026, 5, 9)
        state = _make_state(articles=articles, run_date=run_date)

        result = agent._generate_report_node(state)

        agent._reporter_chain.run.assert_called_once_with(articles, run_date)
        assert result["final_report"] == "# レポート"

    def test_uses_today_when_run_date_missing(self):
        agent = _make_agent()
        agent._reporter_chain.run.return_value = "# レポート"
        state = _make_state()
        state.pop("run_date", None)  # type: ignore[misc]

        result = agent._generate_report_node(state)

        assert result["final_report"] == "# レポート"
        assert agent._reporter_chain.run.called


# ─── publish node ─────────────────────────────────────────────────────────────


class TestPublishNode:
    def test_publish_is_stub_and_returns_empty_dict(self):
        agent = _make_agent()
        state = _make_state(final_report="# レポート")
        result = agent._publish_node(state)

        assert result == {}


# ─── Graph invocation (integration with mocked chains) ───────────────────────


class TestGraphInvocation:
    def _setup_agent_for_happy_path(self) -> CollectAgent:
        agent = _make_agent()

        articles = [
            _make_article(title=f"Article {i}", url=f"https://example.com/{i}")
            for i in range(6)
        ]
        agent._blog_chain.run.return_value = articles[:3]
        agent._github_chain.run.return_value = articles[3:5]
        agent._twitter_chain.run.return_value = articles[5:]

        filtered = [a.model_copy(update={"is_related": True}) for a in articles]
        agent._filter_chain.run.return_value = filtered
        agent._summarizer_chain.run.side_effect = lambda a: a.model_copy(
            update={"summary": "要約テキスト"}
        )

        agent._evaluate_chain.invoke.return_value = _EvaluationResult(
            need_more=False, tip_count=5, reason="十分"
        )
        agent._reporter_chain.run.return_value = "# AI Tips & News — 2026-05-09\n\nレポート内容"

        return agent

    def test_graph_returns_final_report(self):
        agent = self._setup_agent_for_happy_path()
        result = agent.graph.invoke({"run_date": date(2026, 5, 9)})

        assert "final_report" in result
        assert isinstance(result["final_report"], str)
        assert len(result["final_report"]) > 0

    def test_graph_output_contains_report_string(self):
        agent = self._setup_agent_for_happy_path()
        result = agent.graph.invoke({"run_date": date(2026, 5, 9)})

        assert "AI Tips" in result["final_report"]

    def test_retry_loop_stops_at_max_retries(self):
        agent = _make_agent()

        agent._blog_chain.run.return_value = []
        agent._github_chain.run.return_value = []
        agent._filter_chain.run.return_value = []
        agent._reporter_chain.run.return_value = "# empty report"

        # Always says need_more to trigger retries
        agent._evaluate_chain.invoke.return_value = _EvaluationResult(
            need_more=True, tip_count=0, reason="記事が不足"
        )

        result = agent.graph.invoke({"run_date": date(2026, 5, 9)})

        # Verify loop terminates and returns a report
        assert "final_report" in result
        # evaluate should be called: 1 (initial) + max_retry_loops (3 retries) = 4 times
        max_retries = 3  # settings.collector.max_retry_loops
        assert agent._evaluate_chain.invoke.call_count == max_retries + 1

    def test_graph_mermaid_diagram_generated(self):
        agent = _make_agent()
        # Should be able to get the Mermaid graph representation
        mermaid = agent.graph.get_graph().draw_mermaid()
        assert "dispatch_collect" in mermaid
        assert "collect_twitter" in mermaid
        assert "filter_and_summarize" in mermaid
        assert "evaluate" in mermaid
        assert "generate_report" in mermaid

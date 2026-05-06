"""filter_chain.py のユニットテスト（LLM呼び出しをモック）"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from chains.filter_chain import FilterChain, _FilterResult
from models.article import Article


def _make_article(
    title: str = "Claude Code の使い方",
    source: str = "anthropic",
    raw_content: str = "Claude Code を使ったコーディングの実践ガイドです。",
    **kwargs,
) -> Article:
    return Article(
        title=title,
        url="https://example.com/article",
        source=source,
        raw_content=raw_content,
        **kwargs,
    )


def _make_chain() -> FilterChain:
    with patch("chains.filter_chain.ChatAnthropic"), patch(
        "chains.filter_chain.ChatPromptTemplate"
    ):
        chain = FilterChain.__new__(FilterChain)
    return chain


class TestFilterChainRun:
    def test_sets_is_related_true(self):
        chain = _make_chain()
        chain._chain = MagicMock()
        chain._chain.invoke.return_value = _FilterResult(
            is_related=True, reason="AIコーディングに関連する記事です。"
        )

        article = _make_article()
        results = chain.run([article])

        assert len(results) == 1
        assert results[0].is_related is True
        assert results[0].relevance_score == 1.0

    def test_sets_is_related_false(self):
        chain = _make_chain()
        chain._chain = MagicMock()
        chain._chain.invoke.return_value = _FilterResult(
            is_related=False, reason="生成AIと関係のない記事です。"
        )

        article = _make_article(title="天気予報", raw_content="今日は晴れです。")
        results = chain.run([article])

        assert results[0].is_related is False
        assert results[0].relevance_score == 0.0

    def test_returns_same_length_list(self):
        chain = _make_chain()
        chain._chain = MagicMock()
        chain._chain.invoke.return_value = _FilterResult(is_related=True, reason="関連あり")

        articles = [_make_article(title=f"Article {i}") for i in range(5)]
        results = chain.run(articles)

        assert len(results) == len(articles)

    def test_preserves_other_fields(self):
        chain = _make_chain()
        chain._chain = MagicMock()
        chain._chain.invoke.return_value = _FilterResult(is_related=True, reason="関連あり")

        article = _make_article(title="Test", source="openai")
        results = chain.run([article])

        assert results[0].title == "Test"
        assert results[0].source == "openai"

    def test_error_during_evaluation_returns_is_related_false(self):
        chain = _make_chain()
        chain._chain = MagicMock()
        chain._chain.invoke.side_effect = Exception("API error")

        article = _make_article()
        results = chain.run([article])

        assert results[0].is_related is False

    def test_empty_list_returns_empty(self):
        chain = _make_chain()
        chain._chain = MagicMock()

        results = chain.run([])

        assert results == []

    def test_content_truncated_to_1000_chars(self):
        chain = _make_chain()
        chain._chain = MagicMock()
        chain._chain.invoke.return_value = _FilterResult(is_related=True, reason="関連あり")

        article = _make_article(raw_content="x" * 2000)
        chain.run([article])

        call_kwargs = chain._chain.invoke.call_args[0][0]
        assert len(call_kwargs["content"]) <= 1000

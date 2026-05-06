"""summarizer_chain.py のユニットテスト（LLM呼び出しをモック）"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from chains.summarizer_chain import SummarizerChain
from models.article import Article


def _make_article(
    title: str = "Claude Code の使い方",
    source: str = "anthropic",
    raw_content: str = "Claude Code を使ったコーディングの実践ガイドです。" * 10,
    is_related: bool = True,
) -> Article:
    return Article(
        title=title,
        url="https://example.com/article",
        source=source,
        raw_content=raw_content,
        is_related=is_related,
    )


def _make_chain() -> SummarizerChain:
    with patch("chains.summarizer_chain.ChatAnthropic"), patch(
        "chains.summarizer_chain.ChatPromptTemplate"
    ):
        chain = SummarizerChain.__new__(SummarizerChain)
    return chain


class TestSummarizerChainRun:
    def test_sets_summary_for_related_article(self):
        chain = _make_chain()
        mock_response = MagicMock()
        mock_response.content = "Claude Codeはターミナルで動作するAIコーディングツールです。"
        chain._chain = MagicMock()
        chain._chain.invoke.return_value = mock_response

        article = _make_article()
        result = chain.run(article)

        assert result.summary == "Claude Codeはターミナルで動作するAIコーディングツールです。"

    def test_skips_unrelated_article(self):
        chain = _make_chain()
        chain._chain = MagicMock()

        article = _make_article(is_related=False)
        result = chain.run(article)

        chain._chain.invoke.assert_not_called()
        assert result.summary == ""

    def test_preserves_other_fields(self):
        chain = _make_chain()
        mock_response = MagicMock()
        mock_response.content = "要約テキスト"
        chain._chain = MagicMock()
        chain._chain.invoke.return_value = mock_response

        article = _make_article(title="Test Article", source="openai")
        result = chain.run(article)

        assert result.title == "Test Article"
        assert result.source == "openai"

    def test_summary_truncated_to_max_chars(self, monkeypatch):
        chain = _make_chain()
        mock_response = MagicMock()
        mock_response.content = "要" * 600
        chain._chain = MagicMock()
        chain._chain.invoke.return_value = mock_response

        monkeypatch.setattr(
            "chains.summarizer_chain.settings",
            MagicMock(
                anthropic_api_key="test",
                collector=MagicMock(summary_max_chars=500),
            ),
        )

        article = _make_article()
        result = chain.run(article)

        assert len(result.summary) <= 500

    def test_content_truncated_to_2000_chars(self):
        chain = _make_chain()
        mock_response = MagicMock()
        mock_response.content = "要約"
        chain._chain = MagicMock()
        chain._chain.invoke.return_value = mock_response

        article = _make_article(raw_content="x" * 3000)
        chain.run(article)

        call_kwargs = chain._chain.invoke.call_args[0][0]
        assert len(call_kwargs["content"]) <= 2000

    def test_returns_article_on_api_error(self):
        chain = _make_chain()
        chain._chain = MagicMock()
        chain._chain.invoke.side_effect = Exception("API timeout")

        article = _make_article()
        result = chain.run(article)

        assert isinstance(result, Article)
        assert result.summary == ""

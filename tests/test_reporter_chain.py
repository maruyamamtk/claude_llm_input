"""reporter_chain.py のユニットテスト（LLM呼び出しをモック）"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from chains.reporter_chain import ReporterChain, _format_articles
from models.article import Article


def _make_article(
    title: str = "Claude Code の実践ガイド",
    url: str = "https://example.com/article",
    source: str = "anthropic",
    category: str = "anthropic",
    summary: str = "Claude Codeを使ったコーディングのノウハウ。",
    is_related: bool = True,
) -> Article:
    return Article(
        title=title,
        url=url,
        source=source,
        published_at=datetime(2026, 5, 7, 9, 0, 0, tzinfo=timezone.utc),
        summary=summary,
        is_related=is_related,
        category=category,  # type: ignore[arg-type]
    )


def _make_chain() -> ReporterChain:
    with patch("chains.reporter_chain.ChatGoogleGenerativeAI"), patch(
        "chains.reporter_chain.ChatPromptTemplate"
    ):
        chain = ReporterChain.__new__(ReporterChain)
    return chain


class TestFormatArticles:
    def test_formats_single_article(self):
        article = _make_article()
        text = _format_articles([article])

        assert "Claude Code の実践ガイド" in text
        assert "https://example.com/article" in text
        assert "Claude Codeを使ったコーディングのノウハウ。" in text

    def test_skips_article_without_summary(self):
        article = _make_article(summary="")
        text = _format_articles([article])

        assert text == "(記事なし)"

    def test_separates_multiple_articles(self):
        articles = [
            _make_article(title="Article 1", summary="要約1"),
            _make_article(title="Article 2", summary="要約2"),
        ]
        text = _format_articles(articles)

        assert "Article 1" in text
        assert "Article 2" in text
        assert "---" in text


class TestReporterChainRun:
    def test_returns_markdown_string(self):
        chain = _make_chain()
        mock_response = MagicMock()
        mock_response.content = "# AI Tips & News — 2026-05-07\n\n## 今日のハイライト\n..."
        chain._chain = MagicMock()
        chain._chain.invoke.return_value = mock_response

        articles = [_make_article()]
        result = chain.run(articles, report_date=date(2026, 5, 7))

        assert isinstance(result, str)
        assert "AI Tips" in result

    def test_empty_articles_returns_no_articles_message(self):
        chain = _make_chain()
        chain._chain = MagicMock()

        result = chain.run([], report_date=date(2026, 5, 7))

        chain._chain.invoke.assert_not_called()
        assert "2026-05-07" in result
        assert "記事がありませんでした" in result

    def test_articles_without_summary_returns_no_articles_message(self):
        chain = _make_chain()
        chain._chain = MagicMock()

        articles = [_make_article(summary="")]
        result = chain.run(articles, report_date=date(2026, 5, 7))

        chain._chain.invoke.assert_not_called()
        assert "記事がありませんでした" in result

    def test_uses_today_when_report_date_not_given(self):
        chain = _make_chain()
        mock_response = MagicMock()
        mock_response.content = "# Report"
        chain._chain = MagicMock()
        chain._chain.invoke.return_value = mock_response

        articles = [_make_article()]
        result = chain.run(articles)

        assert isinstance(result, str)
        call_kwargs = chain._chain.invoke.call_args[0][0]
        assert str(date.today()) in call_kwargs["report_date"]

    def test_returns_error_message_on_api_failure(self):
        chain = _make_chain()
        chain._chain = MagicMock()
        chain._chain.invoke.side_effect = Exception("API error")

        articles = [_make_article()]
        result = chain.run(articles, report_date=date(2026, 5, 7))

        assert "失敗" in result

    def test_invoke_receives_formatted_articles(self):
        chain = _make_chain()
        mock_response = MagicMock()
        mock_response.content = "# Report"
        chain._chain = MagicMock()
        chain._chain.invoke.return_value = mock_response

        articles = [_make_article(title="Test Article", summary="テスト要約")]
        chain.run(articles, report_date=date(2026, 5, 7))

        call_kwargs = chain._chain.invoke.call_args[0][0]
        assert "Test Article" in call_kwargs["articles"]
        assert "テスト要約" in call_kwargs["articles"]

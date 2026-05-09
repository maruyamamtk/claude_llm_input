"""twitter_chain.py のユニットテスト（Playwright をモック）"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from chains.twitter_chain import TwitterChain
from models.article import Article

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_MINIMAL_CONFIG = {
    "twitter_accounts": [
        {"handle": "AnthropicAI", "description": "Anthropic公式"},
        {"handle": "OpenAI", "description": "OpenAI公式"},
    ],
    "twitter_settings": {},
}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _ago_iso(hours: float) -> str:
    dt = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _make_chain() -> TwitterChain:
    chain = TwitterChain.__new__(TwitterChain)
    chain.accounts = _MINIMAL_CONFIG["twitter_accounts"]
    chain.max_articles = 10
    return chain


def _make_tweet_element(
    datetime_str: str | None = None,
    text: str = "AI最新情報",
    url: str = "https://x.com/testuser/status/123",
) -> MagicMock:
    """モックツイート要素を生成する。"""
    el = MagicMock()

    # time要素
    time_el = MagicMock()
    time_el.get_attribute.return_value = datetime_str or _now_iso()
    el.query_selector.side_effect = lambda selector: {
        "time": time_el,
        "[data-testid='tweetText']": _make_text_el(text),
        "a[href*='/status/']": _make_link_el(url),
    }.get(selector)

    return el


def _make_text_el(text: str) -> MagicMock:
    el = MagicMock()
    el.inner_text.return_value = text
    return el


def _make_link_el(url: str) -> MagicMock:
    el = MagicMock()
    href = url.replace("https://x.com", "") if url.startswith("https://x.com") else url
    el.get_attribute.return_value = href
    return el


# ---------------------------------------------------------------------------
# Tests: _parse_datetime
# ---------------------------------------------------------------------------


class TestParseDatetime:
    def test_parses_z_suffix(self):
        dt = TwitterChain._parse_datetime("2025-05-06T10:00:00.000Z")
        assert dt == datetime(2025, 5, 6, 10, 0, 0, tzinfo=timezone.utc)

    def test_parses_offset(self):
        dt = TwitterChain._parse_datetime("2025-05-06T10:00:00+00:00")
        assert dt == datetime(2025, 5, 6, 10, 0, 0, tzinfo=timezone.utc)

    def test_returns_none_for_none(self):
        assert TwitterChain._parse_datetime(None) is None

    def test_returns_none_for_invalid(self):
        assert TwitterChain._parse_datetime("not-a-date") is None


# ---------------------------------------------------------------------------
# Tests: _extract_tweets
# ---------------------------------------------------------------------------


class TestExtractTweets:
    def _make_page(self, tweet_elements: list[MagicMock]) -> MagicMock:
        page = MagicMock()
        page.query_selector_all.return_value = tweet_elements
        return page

    def test_returns_articles_within_24h(self):
        chain = _make_chain()
        tweet_el = _make_tweet_element(
            datetime_str=_ago_iso(1),
            text="Recent tweet",
            url="/testuser/status/001",
        )
        page = self._make_page([tweet_el])
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        articles = chain._extract_tweets(page, "testuser", cutoff)

        assert len(articles) == 1
        assert isinstance(articles[0], Article)

    def test_excludes_tweets_older_than_24h(self):
        chain = _make_chain()
        tweet_el = _make_tweet_element(
            datetime_str=_ago_iso(48),
            text="Old tweet",
            url="/testuser/status/002",
        )
        page = self._make_page([tweet_el])
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        articles = chain._extract_tweets(page, "testuser", cutoff)

        assert articles == []

    def test_article_fields_populated(self):
        chain = _make_chain()
        tweet_el = _make_tweet_element(
            datetime_str=_ago_iso(2),
            text="Claude Code の最新アップデート情報です",
            url="/anthropicai/status/999",
        )
        page = self._make_page([tweet_el])
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        articles = chain._extract_tweets(page, "AnthropicAI", cutoff)

        a = articles[0]
        assert a.title == "Claude Code の最新アップデート情報です"
        assert a.url == "https://x.com/anthropicai/status/999"
        assert a.source == "@AnthropicAI"
        assert a.category == "twitter"
        assert isinstance(a.published_at, datetime)
        assert a.raw_content == "Claude Code の最新アップデート情報です"

    def test_long_tweet_text_truncated_in_title(self):
        chain = _make_chain()
        long_text = "A" * 200
        tweet_el = _make_tweet_element(
            datetime_str=_ago_iso(1),
            text=long_text,
            url="/testuser/status/001",
        )
        page = self._make_page([tweet_el])
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        articles = chain._extract_tweets(page, "testuser", cutoff)

        assert len(articles[0].title) == 100
        assert len(articles[0].raw_content) == 200

    def test_skips_tweet_without_time_element(self):
        chain = _make_chain()
        tweet_el = MagicMock()
        tweet_el.query_selector.return_value = None  # time要素なし
        page = self._make_page([tweet_el])
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        articles = chain._extract_tweets(page, "testuser", cutoff)

        assert articles == []

    def test_skips_tweet_without_text_element(self):
        chain = _make_chain()
        tweet_el = MagicMock()
        time_el = MagicMock()
        time_el.get_attribute.return_value = _ago_iso(1)

        def query_selector_side_effect(selector: str):
            if selector == "time":
                return time_el
            return None  # テキスト・リンクなし

        tweet_el.query_selector.side_effect = query_selector_side_effect
        page = self._make_page([tweet_el])
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        articles = chain._extract_tweets(page, "testuser", cutoff)

        assert articles == []

    def test_respects_max_articles_limit(self):
        chain = _make_chain()
        chain.max_articles = 3
        tweet_els = [
            _make_tweet_element(
                datetime_str=_ago_iso(1),
                text=f"Tweet {i}",
                url=f"/testuser/status/{i}",
            )
            for i in range(10)
        ]
        page = self._make_page(tweet_els)
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        articles = chain._extract_tweets(page, "testuser", cutoff)

        assert len(articles) <= chain.max_articles


# ---------------------------------------------------------------------------
# Tests: run() — Playwright をモック
# ---------------------------------------------------------------------------


class TestTwitterChainRun:
    def _mock_playwright(self, articles: list[Article]):
        """TwitterChain._fetch_account を直接モックしてPlaywrightを回避する。"""
        return articles

    def test_run_returns_list_of_articles(self):
        chain = _make_chain()
        recent_articles = [
            Article(
                title="Test tweet",
                url="https://x.com/AnthropicAI/status/1",
                source="@AnthropicAI",
                published_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
                raw_content="Test tweet content",
                category="twitter",
            )
        ]

        with patch.object(chain, "_fetch_account", return_value=recent_articles):
            results = chain.run()

        assert isinstance(results, list)
        assert all(isinstance(a, Article) for a in results)

    def test_run_skips_failed_accounts(self):
        chain = _make_chain()

        with patch.object(chain, "_fetch_account", side_effect=Exception("Network error")):
            results = chain.run()

        assert results == []

    def test_run_collects_from_all_accounts(self):
        chain = _make_chain()
        chain.accounts = [
            {"handle": "AnthropicAI", "description": "Anthropic公式"},
            {"handle": "OpenAI", "description": "OpenAI公式"},
        ]
        article_per_account = [
            Article(
                title="Tweet",
                url="https://x.com/user/status/1",
                source="@user",
                published_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
                raw_content="content",
                category="twitter",
            )
        ]

        with patch.object(chain, "_fetch_account", return_value=article_per_account):
            results = chain.run()

        # 2アカウント × 1件ずつ = 2件
        assert len(results) == 2

    def test_run_partial_failure_skips_failed_only(self):
        chain = _make_chain()
        chain.accounts = [
            {"handle": "AnthropicAI", "description": "Anthropic公式"},
            {"handle": "OpenAI", "description": "OpenAI公式"},
        ]
        success_article = Article(
            title="Succeeded",
            url="https://x.com/AnthropicAI/status/1",
            source="@AnthropicAI",
            published_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
            raw_content="content",
            category="twitter",
        )

        call_count = 0

        def side_effect(account: dict) -> list[Article]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [success_article]
            raise Exception("Network error")

        with patch.object(chain, "_fetch_account", side_effect=side_effect):
            results = chain.run()

        assert len(results) == 1
        assert results[0].source == "@AnthropicAI"

    def test_article_source_is_at_handle(self):
        chain = _make_chain()
        chain.accounts = [{"handle": "AnthropicAI", "description": "Anthropic公式"}]
        article = Article(
            title="Test",
            url="https://x.com/AnthropicAI/status/1",
            source="@AnthropicAI",
            published_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
            raw_content="content",
            category="twitter",
        )

        with patch.object(chain, "_fetch_account", return_value=[article]):
            results = chain.run()

        assert results[0].source == "@AnthropicAI"

    def test_article_category_is_twitter(self):
        chain = _make_chain()
        chain.accounts = [{"handle": "OpenAI", "description": "OpenAI公式"}]
        article = Article(
            title="Test",
            url="https://x.com/OpenAI/status/1",
            source="@OpenAI",
            published_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
            raw_content="content",
            category="twitter",
        )

        with patch.object(chain, "_fetch_account", return_value=[article]):
            results = chain.run()

        assert results[0].category == "twitter"

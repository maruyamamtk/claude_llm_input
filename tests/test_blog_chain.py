"""blog_chain.py のユニットテスト（外部HTTP通信をモック）"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from chains.blog_chain import BlogChain
from models.article import Article

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_MINIMAL_CONFIG = {
    "rss_sources": [
        {"name": "Test RSS", "url": "https://example.com/rss", "type": "rss"}
    ],
    "blog_sources": [
        {"name": "Anthropic News", "url": "https://example.com/blog", "type": "html"}
    ],
    "github_repos": [],
    "twitter_accounts": [],
    "twitter_settings": {},
}


def _make_entry(
    title: str = "Test Entry",
    link: str = "https://example.com/post/1",
    summary: str = "Test summary",
    published: str = "Tue, 06 May 2025 00:00:00 +0000",
) -> SimpleNamespace:
    t = time.strptime(published, "%a, %d %b %Y %H:%M:%S %z")
    entry = SimpleNamespace(
        title=title,
        link=link,
        summary=summary,
        published=published,
        published_parsed=t[:6] + (0, 0, 0),
        updated_parsed=None,
    )
    entry.get = lambda key, default=None: getattr(entry, key, default)
    return entry


def _make_feed(entries: list) -> SimpleNamespace:
    feed = SimpleNamespace(entries=entries)
    return feed


# ---------------------------------------------------------------------------
# Tests: _fetch_rss_source
# ---------------------------------------------------------------------------


class TestFetchRssSource:
    def _chain(self) -> BlogChain:
        with patch("builtins.open"), patch("yaml.safe_load", return_value=_MINIMAL_CONFIG):
            chain = BlogChain.__new__(BlogChain)
            chain.rss_sources = _MINIMAL_CONFIG["rss_sources"]
            chain.blog_sources = _MINIMAL_CONFIG["blog_sources"]
            chain.max_articles = 5
            return chain

    def test_returns_list_of_article(self):
        chain = self._chain()
        entry = _make_entry()
        fake_feed = _make_feed([entry])

        with patch("feedparser.parse", return_value=fake_feed):
            results = chain._fetch_rss_source({"name": "Test RSS", "url": "https://example.com/rss"})

        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], Article)

    def test_article_fields_populated(self):
        chain = self._chain()
        entry = _make_entry(title="Hello World", link="https://example.com/hello", summary="desc")
        fake_feed = _make_feed([entry])

        with patch("feedparser.parse", return_value=fake_feed):
            articles = chain._fetch_rss_source({"name": "My Blog", "url": "https://example.com/rss"})

        a = articles[0]
        assert a.title == "Hello World"
        assert a.url == "https://example.com/hello"
        assert a.source == "My Blog"
        assert a.raw_content == "desc"
        assert isinstance(a.published_at, datetime)

    def test_discovers_feed_when_no_entries(self):
        chain = self._chain()
        empty_feed = _make_feed([])
        real_feed = _make_feed([_make_entry()])

        call_count = {"n": 0}

        def fake_parse(url):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return empty_feed
            return real_feed

        with patch("feedparser.parse", side_effect=fake_parse), patch.object(
            chain, "_discover_feed_url", return_value="https://example.com/feed"
        ):
            results = chain._fetch_rss_source({"name": "Blog", "url": "https://example.com/"})

        assert len(results) == 1

    def test_respects_max_articles(self):
        chain = self._chain()
        chain.max_articles = 2
        entries = [_make_entry(title=f"Post {i}", link=f"https://example.com/{i}") for i in range(10)]
        fake_feed = _make_feed(entries)

        with patch("feedparser.parse", return_value=fake_feed):
            results = chain._fetch_rss_source({"name": "Blog", "url": "https://example.com/rss"})

        assert len(results) == 2


# ---------------------------------------------------------------------------
# Tests: _discover_feed_url
# ---------------------------------------------------------------------------


class TestDiscoverFeedUrl:
    def _chain(self) -> BlogChain:
        chain = BlogChain.__new__(BlogChain)
        chain.max_articles = 5
        return chain

    def test_finds_rss_link(self):
        html = (
            '<html><head>'
            '<link rel="alternate" type="application/rss+xml" href="/feed.rss">'
            '</head></html>'
        )
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        chain = self._chain()
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            result = chain._discover_feed_url("https://example.com/")

        assert result == "https://example.com/feed.rss"

    def test_returns_none_when_no_feed_link(self):
        html = "<html><head><title>No feed</title></head></html>"
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        chain = self._chain()
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            result = chain._discover_feed_url("https://example.com/")

        assert result is None

    def test_returns_none_on_http_error(self):
        chain = self._chain()
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = Exception("timeout")
            mock_client_cls.return_value = mock_client

            result = chain._discover_feed_url("https://example.com/")

        assert result is None


# ---------------------------------------------------------------------------
# Tests: _fetch_html_source
# ---------------------------------------------------------------------------


class TestFetchHtmlSource:
    def _chain(self) -> BlogChain:
        chain = BlogChain.__new__(BlogChain)
        chain.max_articles = 10
        return chain

    def _mock_response(self, html: str) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_extracts_articles_from_html(self):
        html = """
        <html><body>
          <a href="/post/1">First Article About AI</a>
          <a href="/post/2">Second Article on ML</a>
        </body></html>
        """
        chain = self._chain()
        source = {"name": "Anthropic News", "url": "https://example.com/blog"}

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = self._mock_response(html)
            mock_client_cls.return_value = mock_client

            results = chain._fetch_html_source(source)

        assert len(results) == 2
        assert all(isinstance(a, Article) for a in results)
        assert results[0].title == "First Article About AI"
        assert results[0].url == "https://example.com/post/1"
        assert results[0].source == "Anthropic News"
        assert results[0].category == "anthropic"

    def test_skips_external_links(self):
        html = """
        <html><body>
          <a href="/internal">Internal Article About AI</a>
          <a href="https://other.com/external">External Article</a>
        </body></html>
        """
        chain = self._chain()
        source = {"name": "Test Blog", "url": "https://example.com/blog"}

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = self._mock_response(html)
            mock_client_cls.return_value = mock_client

            results = chain._fetch_html_source(source)

        assert all(a.url.startswith("https://example.com") for a in results)

    def test_returns_empty_on_http_error(self):
        chain = self._chain()
        source = {"name": "Test Blog", "url": "https://example.com/blog"}

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = Exception("connection error")
            mock_client_cls.return_value = mock_client

            results = chain._fetch_html_source(source)

        assert results == []


# ---------------------------------------------------------------------------
# Tests: run() integration
# ---------------------------------------------------------------------------


class TestBlogChainRun:
    def test_run_returns_list_of_article(self):
        with patch("builtins.open"), patch("yaml.safe_load", return_value=_MINIMAL_CONFIG):
            chain = BlogChain.__new__(BlogChain)
            chain.rss_sources = _MINIMAL_CONFIG["rss_sources"]
            chain.blog_sources = _MINIMAL_CONFIG["blog_sources"]
            chain.max_articles = 5

        entry = _make_entry()
        fake_feed = _make_feed([entry])

        html = '<html><body><a href="/post/1">An Article About AI Models</a></body></html>'
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        with patch("feedparser.parse", return_value=fake_feed), patch(
            "httpx.Client"
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            results = chain.run()

        assert isinstance(results, list)
        assert all(isinstance(a, Article) for a in results)
        assert all(hasattr(a, "title") for a in results)
        assert all(hasattr(a, "url") for a in results)
        assert all(hasattr(a, "source") for a in results)
        assert all(hasattr(a, "published_at") for a in results)
        assert all(hasattr(a, "raw_content") for a in results)

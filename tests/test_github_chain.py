"""github_chain.py のユニットテスト（外部HTTP通信をモック）"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from chains.github_chain import GithubChain
from models.article import Article

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_MINIMAL_CONFIG = {
    "github_repos": [
        {"repo": "anthropics/anthropic-sdk-python", "description": "Anthropic SDK更新"},
        {"repo": "openai/openai-python", "description": "OpenAI SDK更新"},
    ],
    "rss_sources": [],
    "blog_sources": [],
    "twitter_accounts": [],
    "twitter_settings": {},
}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _ago_iso(hours: float) -> str:
    dt = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    return dt.isoformat().replace("+00:00", "Z")


def _make_release(
    name: str = "v1.0.0",
    tag: str = "v1.0.0",
    html_url: str = "https://github.com/owner/repo/releases/tag/v1.0.0",
    body: str = "Release notes",
    published_at: str | None = None,
) -> dict:
    return {
        "name": name,
        "tag_name": tag,
        "html_url": html_url,
        "body": body,
        "published_at": published_at or _now_iso(),
    }


def _make_chain() -> GithubChain:
    chain = GithubChain.__new__(GithubChain)
    chain.repos = _MINIMAL_CONFIG["github_repos"]
    chain.max_articles = 10
    return chain


# ---------------------------------------------------------------------------
# Tests: _parse_datetime
# ---------------------------------------------------------------------------


class TestParseDatetime:
    def test_parses_z_suffix(self):
        dt = GithubChain._parse_datetime("2025-05-06T10:00:00Z")
        assert dt == datetime(2025, 5, 6, 10, 0, 0, tzinfo=timezone.utc)

    def test_parses_offset(self):
        dt = GithubChain._parse_datetime("2025-05-06T10:00:00+00:00")
        assert dt == datetime(2025, 5, 6, 10, 0, 0, tzinfo=timezone.utc)

    def test_returns_none_for_none(self):
        assert GithubChain._parse_datetime(None) is None

    def test_returns_none_for_invalid(self):
        assert GithubChain._parse_datetime("not-a-date") is None


# ---------------------------------------------------------------------------
# Tests: _fetch_releases
# ---------------------------------------------------------------------------


class TestFetchReleases:
    def _mock_client(self, releases: list[dict]) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.json.return_value = releases
        mock_resp.raise_for_status = MagicMock()
        client = MagicMock()
        client.get.return_value = mock_resp
        return client

    def test_returns_articles_within_24h(self):
        chain = _make_chain()
        recent_release = _make_release(name="v2.0.0", published_at=_ago_iso(1))
        client = self._mock_client([recent_release])
        repo = {"repo": "anthropics/anthropic-sdk-python", "description": "Anthropic SDK更新"}
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        articles = chain._fetch_releases(client, repo, cutoff)

        assert len(articles) == 1
        assert isinstance(articles[0], Article)

    def test_excludes_releases_older_than_24h(self):
        chain = _make_chain()
        old_release = _make_release(name="v1.0.0", published_at=_ago_iso(48))
        client = self._mock_client([old_release])
        repo = {"repo": "anthropics/anthropic-sdk-python", "description": "Anthropic SDK更新"}
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        articles = chain._fetch_releases(client, repo, cutoff)

        assert len(articles) == 0

    def test_stops_at_first_old_release(self):
        chain = _make_chain()
        releases = [
            _make_release(name="v3.0.0", published_at=_ago_iso(1)),
            _make_release(name="v2.0.0", published_at=_ago_iso(48)),  # old
            _make_release(name="v1.0.0", published_at=_ago_iso(72)),  # old
        ]
        client = self._mock_client(releases)
        repo = {"repo": "test/repo", "description": "Test"}
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        articles = chain._fetch_releases(client, repo, cutoff)

        assert len(articles) == 1
        assert articles[0].title.endswith("v3.0.0")

    def test_article_fields_populated(self):
        chain = _make_chain()
        release = _make_release(
            name="v2.0.0",
            tag="v2.0.0",
            html_url="https://github.com/anthropics/anthropic-sdk-python/releases/tag/v2.0.0",
            body="## Changes\n- fix: bug fix",
            published_at=_ago_iso(2),
        )
        client = self._mock_client([release])
        repo = {"repo": "anthropics/anthropic-sdk-python", "description": "Anthropic SDK更新"}
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        articles = chain._fetch_releases(client, repo, cutoff)

        a = articles[0]
        assert a.title == "[anthropics/anthropic-sdk-python] v2.0.0"
        assert a.url == "https://github.com/anthropics/anthropic-sdk-python/releases/tag/v2.0.0"
        assert a.source == "Anthropic SDK更新"
        assert a.raw_content == "## Changes\n- fix: bug fix"
        assert a.category == "github"
        assert isinstance(a.published_at, datetime)

    def test_returns_empty_on_api_error(self):
        chain = _make_chain()
        client = MagicMock()
        client.get.side_effect = Exception("API error")
        repo = {"repo": "test/repo", "description": "Test"}
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        articles = chain._fetch_releases(client, repo, cutoff)

        assert articles == []

    def test_skips_draft_releases(self):
        chain = _make_chain()
        draft_release = {
            "name": "v2.0.0-draft",
            "tag_name": "v2.0.0-draft",
            "html_url": "https://github.com/test/repo/releases/tag/v2.0.0-draft",
            "body": "",
            "published_at": None,
            "draft": True,
        }
        recent_release = _make_release(name="v1.0.0", published_at=_ago_iso(1))
        client = self._mock_client([draft_release, recent_release])
        repo = {"repo": "test/repo", "description": "Test"}
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        articles = chain._fetch_releases(client, repo, cutoff)

        # draft はスキップされ、recent_release のみ収集される
        assert len(articles) == 1
        assert "v1.0.0" in articles[0].title

    def test_excludes_release_with_no_published_at(self):
        chain = _make_chain()
        release = {
            "name": "v1.0.0",
            "tag_name": "v1.0.0",
            "html_url": "https://github.com/test/repo/releases/tag/v1.0.0",
            "body": "",
            "published_at": None,
            "draft": False,
        }
        client = self._mock_client([release])
        repo = {"repo": "test/repo", "description": "Test"}
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        articles = chain._fetch_releases(client, repo, cutoff)

        assert len(articles) == 0

    def test_uses_tag_name_when_name_is_none(self):
        chain = _make_chain()
        release = {
            "name": None,
            "tag_name": "v1.5.0",
            "html_url": "https://github.com/test/repo/releases/tag/v1.5.0",
            "body": "",
            "published_at": _ago_iso(1),
        }
        client = self._mock_client([release])
        repo = {"repo": "test/repo", "description": "Test"}
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        articles = chain._fetch_releases(client, repo, cutoff)

        assert "v1.5.0" in articles[0].title


# ---------------------------------------------------------------------------
# Tests: run()
# ---------------------------------------------------------------------------


class TestGithubChainRun:
    def test_run_returns_list_of_article(self):
        chain = _make_chain()
        recent_release = _make_release(name="v2.0.0", published_at=_ago_iso(1))
        mock_resp = MagicMock()
        mock_resp.json.return_value = [recent_release]
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            results = chain.run()

        assert isinstance(results, list)
        assert all(isinstance(a, Article) for a in results)

    def test_run_collects_from_all_repos(self):
        chain = _make_chain()
        chain.repos = [
            {"repo": "repo1/pkg", "description": "Repo 1"},
            {"repo": "repo2/pkg", "description": "Repo 2"},
        ]
        recent_release = _make_release(name="v1.0.0", published_at=_ago_iso(1))
        mock_resp = MagicMock()
        mock_resp.json.return_value = [recent_release]
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            results = chain.run()

        # 2 repos × 1 release each = 2 articles
        assert len(results) == 2

    def test_run_article_required_fields_exist(self):
        chain = _make_chain()
        chain.repos = [{"repo": "test/repo", "description": "Test Repo"}]
        release = _make_release(published_at=_ago_iso(1))
        mock_resp = MagicMock()
        mock_resp.json.return_value = [release]
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            results = chain.run()

        a = results[0]
        assert a.title != ""
        assert a.url != ""
        assert a.source != ""
        assert a.published_at is not None
        assert isinstance(a.raw_content, str)

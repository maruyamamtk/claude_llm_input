from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Literal, Optional
from urllib.parse import urljoin, urlparse

import logging

import feedparser
import httpx
import yaml

from models.article import Article
from settings import settings

logger = logging.getLogger(__name__)

_CATEGORY_MAP: dict[str, Literal["anthropic", "openai", "github", "blog", "twitter", "other"]] = {
    "anthropic news": "anthropic",
    "openai news": "openai",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class _HtmlParser(HTMLParser):
    """Extract RSS/Atom feed links and article <a> tags from HTML."""

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.feed_urls: list[str] = []
        self.links: list[tuple[str, str]] = []  # (href, text)
        self._in_anchor = False
        self._current_href = ""
        self._current_text = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        d = dict(attrs)

        if tag == "link":
            rel = d.get("rel", "") or ""
            content_type = d.get("type", "") or ""
            href = d.get("href", "") or ""
            if "alternate" in rel and ("rss" in content_type or "atom" in content_type) and href:
                self.feed_urls.append(self._absolute(href))

        if tag == "a":
            self._current_href = self._absolute(d.get("href", "") or "")
            self._in_anchor = True
            self._current_text = ""

    def handle_data(self, data: str) -> None:
        if self._in_anchor:
            self._current_text += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_anchor:
            text = self._current_text.strip()
            if self._current_href and text:
                self.links.append((self._current_href, text))
            self._in_anchor = False
            self._current_href = ""
            self._current_text = ""

    def _absolute(self, href: str) -> str:
        if not href:
            return ""
        if href.startswith("http"):
            return href
        return urljoin(self.base_url, href)


class BlogChain:
    def __init__(self, config_path: str = "config.yaml") -> None:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        self.rss_sources: list[dict] = config.get("rss_sources", [])
        self.blog_sources: list[dict] = config.get("blog_sources", [])
        self.max_articles: int = settings.collector.max_articles_per_source

    def run(self) -> list[Article]:
        articles: list[Article] = []
        for source in self.rss_sources:
            articles.extend(self._fetch_rss_source(source))
        for source in self.blog_sources:
            articles.extend(self._fetch_html_source(source))
        return articles

    # ------------------------------------------------------------------
    # RSS / Atom
    # ------------------------------------------------------------------

    def _fetch_rss_source(self, source: dict) -> list[Article]:
        url: str = source["url"]
        name: str = source["name"]

        feed = feedparser.parse(url)

        if not feed.entries:
            feed_url = self._discover_feed_url(url)
            if feed_url:
                feed = feedparser.parse(feed_url)

        articles: list[Article] = []
        for entry in feed.entries[: self.max_articles]:
            published_at = self._parse_time(
                entry.get("published_parsed") or entry.get("updated_parsed")
            )
            articles.append(
                Article(
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    source=name,
                    published_at=published_at,
                    raw_content=entry.get("summary", ""),
                    category=self._category(name),
                )
            )
        return articles

    def _discover_feed_url(self, url: str) -> Optional[str]:
        """Fetch the page and look for <link rel="alternate"> pointing to a feed."""
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True, headers=_HEADERS) as client:
                response = client.get(url)
                response.raise_for_status()
            parser = _HtmlParser(url)
            parser.feed(response.text)
            if parser.feed_urls:
                return parser.feed_urls[0]
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # HTML scraping
    # ------------------------------------------------------------------

    def _fetch_html_source(self, source: dict) -> list[Article]:
        url: str = source["url"]
        name: str = source["name"]
        base_netloc = urlparse(url).netloc

        try:
            with httpx.Client(timeout=15.0, follow_redirects=True, headers=_HEADERS) as client:
                response = client.get(url)
                response.raise_for_status()
        except Exception as exc:
            logger.warning("[BlogChain] HTML fetch failed for %s: %s", name, exc)
            return []

        parser = _HtmlParser(url)
        parser.feed(response.text)

        seen: set[str] = set()
        articles: list[Article] = []

        for href, title in parser.links:
            if len(articles) >= self.max_articles:
                break
            if not href.startswith("http"):
                continue
            if urlparse(href).netloc != base_netloc:
                continue
            if href in seen or len(title) < 5:
                continue
            seen.add(href)
            articles.append(
                Article(
                    title=title,
                    url=href,
                    source=name,
                    published_at=None,
                    raw_content="",
                    category=self._category(name),
                )
            )

        return articles

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_time(
        t: Optional[tuple],
    ) -> Optional[datetime]:
        if t is None:
            return None
        try:
            return datetime(*t[:6], tzinfo=timezone.utc)
        except Exception:
            return None

    @staticmethod
    def _category(
        name: str,
    ) -> Literal["anthropic", "openai", "github", "blog", "twitter", "other"]:
        return _CATEGORY_MAP.get(name.lower(), "blog")

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx
import yaml
from playwright.sync_api import sync_playwright
from tenacity import retry, stop_after_attempt, wait_exponential

from models.article import Article
from settings import settings

logger = logging.getLogger(__name__)

_CUTOFF_HOURS = 24
_TCO_RE = re.compile(r"https?://t\.co/\S+")
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class TwitterChain:
    def __init__(self, config_path: str = "config.yaml") -> None:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        self.accounts: list[dict] = config.get("twitter_accounts", [])
        self.max_articles: int = settings.collector.max_articles_per_source
        twitter_settings = config.get("twitter_settings", {})
        self.follow_links: bool = twitter_settings.get("follow_links", False)
        self.max_linked_articles: int = twitter_settings.get("max_linked_articles", 3)

    def run(self) -> list[Article]:
        articles: list[Article] = []
        seen_urls: set[str] = set()

        for account in self.accounts:
            try:
                fetched = self._fetch_account(account)
                for a in fetched:
                    seen_urls.add(a.url)
                articles.extend(fetched)
            except Exception as exc:
                logger.warning(
                    "[TwitterChain] スキップ @%s: %s", account.get("handle", "?"), exc
                )

        if self.follow_links and articles:
            linked = self._fetch_linked_articles(articles, seen_urls)
            articles.extend(linked)

        return articles

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _fetch_account(self, account: dict) -> list[Article]:
        handle: str = account["handle"]
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=_CUTOFF_HOURS)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=_USER_AGENT,
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            try:
                page.goto(f"https://x.com/{handle}", timeout=30_000)
                page.wait_for_selector("[data-testid='tweet']", timeout=15_000)
                articles = self._extract_tweets(page, handle, cutoff)
            finally:
                browser.close()

        return articles

    def _extract_tweets(self, page, handle: str, cutoff: datetime) -> list[Article]:
        articles: list[Article] = []

        tweet_elements = page.query_selector_all("[data-testid='tweet']")
        for tweet_el in tweet_elements:
            if len(articles) >= self.max_articles:
                break

            time_el = tweet_el.query_selector("time")
            if not time_el:
                continue
            published_at = self._parse_datetime(time_el.get_attribute("datetime"))
            if published_at is None or published_at < cutoff:
                continue

            text_el = tweet_el.query_selector("[data-testid='tweetText']")
            if not text_el:
                continue
            text = text_el.inner_text().strip()
            if not text:
                continue

            link_el = tweet_el.query_selector("a[href*='/status/']")
            if not link_el:
                continue
            href = link_el.get_attribute("href") or ""
            url = f"https://x.com{href}" if href.startswith("/") else href
            if not url:
                continue

            title = text[:100].replace("\n", " ").strip()
            articles.append(
                Article(
                    title=title,
                    url=url,
                    source=f"@{handle}",
                    published_at=published_at,
                    raw_content=text,
                    category="twitter",
                )
            )

        return articles

    def _extract_urls_from_text(self, text: str) -> list[str]:
        """ツイート本文から t.co 短縮 URL を抽出する。"""
        return _TCO_RE.findall(text)

    def _expand_url(self, url: str) -> str:
        """t.co 短縮 URL をリダイレクト追跡して実際の URL を返す。"""
        try:
            with httpx.Client(
                timeout=10.0,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                resp = client.head(url)
                return str(resp.url)
        except Exception:
            return url

    def _fetch_linked_articles(
        self, tweet_articles: list[Article], seen_urls: set[str]
    ) -> list[Article]:
        """各ツイートに含まれる外部リンクをスクレイピングして Article リストを返す。"""
        urls_to_fetch: list[tuple[str, str]] = []  # (real_url, source)

        for tweet_article in tweet_articles:
            if not tweet_article.raw_content:
                continue
            tco_urls = self._extract_urls_from_text(tweet_article.raw_content)
            count = 0
            for tco_url in tco_urls:
                if count >= self.max_linked_articles:
                    break
                real_url = self._expand_url(tco_url)
                parsed = urlparse(real_url)
                if parsed.netloc in ("x.com", "twitter.com", "www.x.com", "www.twitter.com"):
                    continue
                if real_url in seen_urls:
                    continue
                seen_urls.add(real_url)
                urls_to_fetch.append((real_url, tweet_article.source))
                count += 1

        if not urls_to_fetch:
            return []

        linked: list[Article] = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=_USER_AGENT,
                viewport={"width": 1280, "height": 800},
            )
            try:
                for url, source in urls_to_fetch:
                    article = self._scrape_linked_page(context, url, source)
                    if article:
                        linked.append(article)
            finally:
                browser.close()

        return linked

    def _scrape_linked_page(self, context, url: str, source: str) -> Optional[Article]:
        """Playwright でリンク先ページをスクレイピングして Article を返す。"""
        try:
            page = context.new_page()
            try:
                page.goto(url, timeout=30_000)
                title = page.title() or url
                body = page.query_selector("body")
                raw_content = body.inner_text()[:2000].strip() if body else ""
                return Article(
                    title=title[:200],
                    url=url,
                    source=source,
                    published_at=datetime.now(tz=timezone.utc),
                    raw_content=raw_content,
                    category="twitter",
                )
            finally:
                page.close()
        except Exception as exc:
            logger.warning("[TwitterChain] リンク先スクレイピング失敗 %s: %s", url, exc)
            return None

    @staticmethod
    def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            return None

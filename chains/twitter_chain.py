from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import yaml
from tenacity import retry, stop_after_attempt, wait_exponential

from models.article import Article
from settings import settings

logger = logging.getLogger(__name__)

_CUTOFF_HOURS = 24


class TwitterChain:
    def __init__(self, config_path: str = "config.yaml") -> None:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        self.accounts: list[dict] = config.get("twitter_accounts", [])
        self.max_articles: int = settings.collector.max_articles_per_source

    def run(self) -> list[Article]:
        articles: list[Article] = []
        for account in self.accounts:
            try:
                fetched = self._fetch_account(account)
                articles.extend(fetched)
            except Exception as exc:
                logger.warning(
                    "[TwitterChain] スキップ @%s: %s", account.get("handle", "?"), exc
                )
        return articles

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _fetch_account(self, account: dict) -> list[Article]:
        handle: str = account["handle"]
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=_CUTOFF_HOURS)

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
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

    @staticmethod
    def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            return None

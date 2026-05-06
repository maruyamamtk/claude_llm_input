from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import yaml

from models.article import Article
from settings import settings

logger = logging.getLogger(__name__)


class GithubChain:
    _BASE_URL = "https://api.github.com"

    def __init__(self, config_path: str = "config.yaml") -> None:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        self.repos: list[dict] = config.get("github_repos", [])
        self.max_articles: int = settings.collector.max_articles_per_source

    def run(self) -> list[Article]:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
        headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        articles: list[Article] = []
        with httpx.Client(timeout=15.0, headers=headers) as client:
            for repo in self.repos:
                articles.extend(self._fetch_releases(client, repo, cutoff))
        return articles

    def _fetch_releases(
        self,
        client: httpx.Client,
        repo: dict,
        cutoff: datetime,
    ) -> list[Article]:
        repo_name: str = repo["repo"]
        description: str = repo.get("description", repo_name)

        try:
            response = client.get(
                f"{self._BASE_URL}/repos/{repo_name}/releases",
                params={"per_page": self.max_articles},
            )
            response.raise_for_status()
            releases: list[dict] = response.json()
        except Exception as exc:
            logger.warning("[GithubChain] API error for %s: %s", repo_name, exc)
            return []

        articles: list[Article] = []
        for release in releases:
            # Skip draft releases (published_at is None for drafts)
            if release.get("draft"):
                continue

            published_at = self._parse_datetime(release.get("published_at"))
            # Releases without a publish date or older than cutoff are excluded.
            # GitHub returns releases sorted newest first, so stop on the first old one.
            if published_at is None or published_at < cutoff:
                break

            tag = release.get("tag_name", "")
            release_name = release.get("name") or tag
            articles.append(
                Article(
                    title=f"[{repo_name}] {release_name}",
                    url=release.get("html_url", ""),
                    source=description,
                    published_at=published_at,
                    raw_content=release.get("body", "") or "",
                    category="github",
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

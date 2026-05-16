from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

from models.article import Article
from settings import settings

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "reporter_system.prompt"


def _format_articles(articles: list[Article]) -> str:
    lines: list[str] = []
    for a in articles:
        if not a.summary:
            continue
        pub = a.published_at.strftime("%Y-%m-%d") if a.published_at else "日付不明"
        lines.append(
            f"## {a.title}\n"
            f"URL: {a.url}\n"
            f"ソース: {a.source} | カテゴリ: {a.category} | 公開日: {pub}\n"
            f"要約:\n{a.summary}\n"
        )
    return "\n---\n".join(lines) if lines else "(記事なし)"


class ReporterChain:
    def __init__(self) -> None:
        system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.google_api_key,
            thinking_budget=0,
            max_tokens=4096,
        )
        self._chain = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "対象日: {report_date}\n\n収集記事:\n{articles}"),
            ]
        ) | llm

    def run(self, articles: list[Article], report_date: date | None = None) -> str:
        target_date = report_date or date.today()
        summarized = [a for a in articles if a.summary]
        if not summarized:
            return f"# AI Tips & News — {target_date}\n\n本日は収集された記事がありませんでした。\n"
        articles_text = _format_articles(summarized)
        try:
            response = self._chain.invoke(
                {
                    "report_date": str(target_date),
                    "articles": articles_text,
                }
            )
            return response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.error("[ReporterChain] レポート生成失敗: %s", exc)
            return f"# AI Tips & News — {target_date}\n\nレポート生成に失敗しました: {exc}\n"

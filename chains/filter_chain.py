from __future__ import annotations

import logging
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from models.article import Article
from settings import settings

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "filter.prompt"


class _FilterResult(BaseModel):
    is_related: bool = Field(description="生成AI活用・AIコーディングに関連するか")
    reason: str = Field(description="判定理由（日本語1〜2文）")


class FilterChain:
    def __init__(self) -> None:
        system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.google_api_key,
            thinking_budget=0,
            max_tokens=256,
        )
        structured_llm = llm.with_structured_output(_FilterResult)
        self._chain = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "タイトル: {title}\nソース: {source}\n内容: {content}\n\n上記の基準で判定してください。"),
            ]
        ) | structured_llm

    def run(self, articles: list[Article]) -> list[Article]:
        results: list[Article] = []
        for article in articles:
            result = self._evaluate(article)
            updated = article.model_copy(
                update={
                    "is_related": result.is_related,
                    "relevance_score": 1.0 if result.is_related else 0.0,
                }
            )
            results.append(updated)
        return results

    def _evaluate(self, article: Article) -> _FilterResult:
        content = article.raw_content[:1000] if article.raw_content else "(本文なし)"
        try:
            result = self._chain.invoke(
                {
                    "title": article.title,
                    "source": article.source,
                    "content": content,
                }
            )
            return result  # type: ignore[return-value]
        except Exception as exc:
            logger.warning("[FilterChain] 評価失敗 title=%s: %s", article.title, exc)
            return _FilterResult(is_related=False, reason=f"評価エラー: {exc}")

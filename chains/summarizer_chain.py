from __future__ import annotations

import logging
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

from models.article import Article
from settings import settings

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "summarize.prompt"


class SummarizerChain:
    def __init__(self) -> None:
        system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.google_api_key,
            thinking_budget=0,
            max_tokens=600,
        )
        self._chain = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "タイトル: {title}\nソース: {source}\n内容: {content}\n\n上記の記事を要約してください。"),
            ]
        ) | llm

    def run(self, article: Article) -> Article:
        if not article.is_related:
            return article
        content = article.raw_content[:2000] if article.raw_content else "(本文なし)"
        try:
            response = self._chain.invoke(
                {
                    "title": article.title,
                    "source": article.source,
                    "content": content,
                }
            )
            summary = response.content if hasattr(response, "content") else str(response)
            max_chars = settings.collector.summary_max_chars
            return article.model_copy(update={"summary": summary[:max_chars]})
        except Exception as exc:
            logger.warning("[SummarizerChain] 要約失敗 title=%s: %s", article.title, exc)
            return article

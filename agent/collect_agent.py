from __future__ import annotations

import logging
import operator
from datetime import date
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from pydantic import BaseModel, Field

from chains.blog_chain import BlogChain
from chains.filter_chain import FilterChain
from chains.github_chain import GithubChain
from chains.reporter_chain import ReporterChain
from chains.summarizer_chain import SummarizerChain
from chains.twitter_chain import TwitterChain
from models.article import Article
from settings import settings

logger = logging.getLogger(__name__)


# ─── State definitions ────────────────────────────────────────────────────────


class CollectAgentInputState(TypedDict):
    run_date: date


class CollectAgentPrivateState(TypedDict):
    raw_articles: Annotated[list[Article], operator.add]
    articles: list[Article]
    retry_count: int
    evaluation: dict


class CollectAgentOutputState(TypedDict):
    final_report: str


class CollectAgentState(
    CollectAgentInputState, CollectAgentPrivateState, CollectAgentOutputState
):
    pass


# ─── Evaluation schema ────────────────────────────────────────────────────────


class _EvaluationResult(BaseModel):
    need_more: bool = Field(description="追加収集が必要か")
    tip_count: int = Field(description="実践Tipsとして使える記事の件数（概算）")
    reason: str = Field(description="評価理由（日本語1〜2文）")


_EVALUATE_SYSTEM = """\
あなたは情報収集エージェントの品質評価者です。
以下の収集済み記事リストを評価し、追加収集が必要かどうかを判定してください。

判定基準:
1. 実践的なTips・HowToとして活用できる記事が3件以上あること
2. 生成AI活用・AIコーディングに関する過去24時間の重要な更新を十分に網羅していること

収集済み記事:
{article_list}

上記の基準に基づいて評価してください。
"""


# ─── Agent ────────────────────────────────────────────────────────────────────


class CollectAgent:
    def __init__(self) -> None:
        self._blog_chain = BlogChain()
        self._github_chain = GithubChain()
        self._twitter_chain = TwitterChain()
        self._filter_chain = FilterChain()
        self._summarizer_chain = SummarizerChain()
        self._reporter_chain = ReporterChain()
        self._evaluate_chain = self._build_evaluate_chain()
        self.graph = self._build_graph()

    def _build_evaluate_chain(self):
        llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=512,
        )
        structured_llm = llm.with_structured_output(_EvaluationResult)
        return (
            ChatPromptTemplate.from_messages(
                [
                    ("system", _EVALUATE_SYSTEM),
                    ("human", "上記の記事リストを評価してください。"),
                ]
            )
            | structured_llm
        )

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(
            CollectAgentState,
            input_schema=CollectAgentInputState,
            output_schema=CollectAgentOutputState,
        )

        builder.add_node("dispatch_collect", self._dispatch_collect_node)
        builder.add_node("collect_blog", self._collect_blog_node)
        builder.add_node("collect_github", self._collect_github_node)
        builder.add_node("collect_twitter", self._collect_twitter_node)
        builder.add_node("filter_and_summarize", self._filter_and_summarize_node)
        builder.add_node("evaluate", self._evaluate_node)
        builder.add_node("generate_report", self._generate_report_node)
        builder.add_node("publish", self._publish_node)

        builder.add_edge(START, "dispatch_collect")
        builder.add_conditional_edges(
            "dispatch_collect",
            self._dispatch_edges,
            ["collect_blog", "collect_github", "collect_twitter"],
        )
        builder.add_edge("collect_blog", "filter_and_summarize")
        builder.add_edge("collect_github", "filter_and_summarize")
        builder.add_edge("collect_twitter", "filter_and_summarize")
        builder.add_edge("filter_and_summarize", "evaluate")
        builder.add_conditional_edges(
            "evaluate",
            self._evaluate_routing,
            {"collect": "dispatch_collect", "report": "generate_report"},
        )
        builder.add_edge("generate_report", "publish")
        builder.add_edge("publish", END)

        return builder.compile()

    # ── Node implementations ──────────────────────────────────────────────────

    def _dispatch_collect_node(self, state: CollectAgentState) -> dict:
        return {}

    def _dispatch_edges(self, state: CollectAgentState) -> list[Send]:
        return [
            Send("collect_blog", state),
            Send("collect_github", state),
            Send("collect_twitter", state),
        ]

    def _collect_blog_node(self, state: CollectAgentState) -> dict:
        articles = self._blog_chain.run()
        return {"raw_articles": articles}

    def _collect_github_node(self, state: CollectAgentState) -> dict:
        articles = self._github_chain.run()
        return {"raw_articles": articles}

    def _collect_twitter_node(self, state: CollectAgentState) -> dict:
        articles = self._twitter_chain.run()
        return {"raw_articles": articles}

    def _filter_and_summarize_node(self, state: CollectAgentState) -> dict:
        raw = state.get("raw_articles", [])
        seen_urls: set[str] = set()
        unique: list[Article] = []
        for article in raw:
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                unique.append(article)

        filtered = self._filter_chain.run(unique)
        related = [a for a in filtered if a.is_related]
        articles = [self._summarizer_chain.run(a) for a in related]
        return {"articles": articles}

    def _evaluate_node(self, state: CollectAgentState) -> dict:
        articles = state.get("articles", [])
        article_list = (
            "\n".join(
                f"- [{a.category}] {a.title}: {a.summary[:100] if a.summary else '(要約なし)'}"
                for a in articles
            )
            or "(記事なし)"
        )
        try:
            result: _EvaluationResult = self._evaluate_chain.invoke(
                {"article_list": article_list}
            )
            evaluation = {
                "need_more": result.need_more,
                "tip_count": result.tip_count,
                "reason": result.reason,
            }
        except Exception as exc:
            logger.warning("[CollectAgent] 評価失敗: %s", exc)
            evaluation = {
                "need_more": False,
                "tip_count": len(articles),
                "reason": f"評価エラー: {exc}",
            }

        retry_count = state.get("retry_count", 0) + 1
        return {"evaluation": evaluation, "retry_count": retry_count}

    def _evaluate_routing(self, state: CollectAgentState) -> str:
        evaluation = state.get("evaluation", {})
        retry_count = state.get("retry_count", 0)
        max_retries = settings.collector.max_retry_loops
        if evaluation.get("need_more") and retry_count <= max_retries:
            return "collect"
        return "report"

    def _generate_report_node(self, state: CollectAgentState) -> dict:
        articles = state.get("articles", [])
        run_date = state.get("run_date")
        report_date = run_date if isinstance(run_date, date) else date.today()
        final_report = self._reporter_chain.run(articles, report_date)
        return {"final_report": final_report}

    def _publish_node(self, state: CollectAgentState) -> dict:
        collected = len(state.get("raw_articles", []))
        filtered = len(state.get("articles", []))
        retries = state.get("retry_count", 0)
        logger.info(
            "[CollectAgent] 収集件数: %d | フィルタ通過件数: %d | リトライ回数: %d",
            collected,
            filtered,
            retries,
        )
        return {}

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from settings import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
あなたはAI・テクノロジーの専門家アシスタントです。
ユーザーの質問に対して、提供されたObsidianノートのコンテキストを参照しながら日本語で回答してください。

回答は必ず以下のMarkdown形式で出力してください：

**Q**: <ユーザーの質問をそのまま記載>
**A**: 回答（300字以内で簡潔に）
**参照**: [ドキュメントタイトルまたはURL](URL)

注意事項：
- 回答は300字以内に収めること
- コンテキストに関連情報がある場合は必ずURLを参照として含めること
- コンテキストに情報がない場合は一般知識で回答し、参照URLは「N/A」とすること
- 日本語で回答すること
"""

_ANSWER_PROMPT = """\
以下のObsidianノートのコンテキストを参照して質問に回答してください。

## コンテキスト（最新10ファイルの内容）
{context}

## 質問
{question}

上記のシステムプロンプトの形式に従って回答してください。
"""


class QAState(TypedDict):
    question: str
    context: str
    answer: str


class QAAgent:
    def __init__(self) -> None:
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=1024,
        )
        self._notes_dir = Path(settings.obsidian_notes_dir).expanduser()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(QAState)
        builder.add_node("load_context", self._load_context_node)
        builder.add_node("generate_answer", self._generate_answer_node)
        builder.add_edge(START, "load_context")
        builder.add_edge("load_context", "generate_answer")
        builder.add_edge("generate_answer", END)
        return builder.compile()

    def _load_context_node(self, state: QAState) -> dict:
        context = self._load_obsidian_context()
        return {"context": context}

    def _load_obsidian_context(self) -> str:
        if not self._notes_dir.exists():
            logger.warning("[QAAgent] Obsidianノートディレクトリが見つかりません: %s", self._notes_dir)
            return "(Obsidianノートが見つかりませんでした)"

        md_files = sorted(self._notes_dir.glob("*.md"), reverse=True)[:10]
        if not md_files:
            return "(Obsidianノートが見つかりませんでした)"

        parts: list[str] = []
        for file_path in md_files:
            try:
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"### {file_path.name}\n{content[:3000]}")
            except OSError as e:
                logger.warning("[QAAgent] ファイル読み込みエラー: %s - %s", file_path, e)

        logger.info("[QAAgent] %d件のObsidianファイルをロードしました", len(parts))
        return "\n\n---\n\n".join(parts)

    def _generate_answer_node(self, state: QAState) -> dict:
        question = state["question"]
        context = state["context"]

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=_ANSWER_PROMPT.format(context=context, question=question)
            ),
        ]

        try:
            response = self._llm.invoke(messages)
            answer = response.content
        except Exception as exc:
            logger.error("[QAAgent] 回答生成エラー: %s", exc)
            answer = f"**Q**: {question}\n**A**: 回答の生成に失敗しました: {exc}\n**参照**: N/A"

        return {"answer": answer}

    def run(self, question: str) -> str:
        """質問を受け取り、Markdown形式の回答を返す。"""
        result = self.graph.invoke({"question": question, "context": "", "answer": ""})
        return result["answer"]

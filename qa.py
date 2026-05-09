#!/usr/bin/env python3
"""Q&A CLIエントリーポイント。

Usage:
    python qa.py "質問文"
"""
from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from agent.qa_agent import QAAgent
from service.obsidian_writer import ObsidianWriter

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


def _ensure_qa_section(writer: ObsidianWriter, today: date) -> None:
    """当日ファイルが存在しない場合、Q&Aログセクション付きで新規作成する。"""
    notes_dir = Path(writer._dir)
    file_path = notes_dir / f"{today.isoformat()}_ai_tips.md"
    if not file_path.exists():
        initial_content = f"# AI Tips {today.isoformat()}\n\n## Q&A ログ\n"
        writer.write(initial_content, target_date=today)


def _append_qa_log(writer: ObsidianWriter, qa_entry: str, today: date) -> None:
    """Q&Aログセクションがない場合は追加してからエントリを追記する。"""
    notes_dir = Path(writer._dir)
    file_path = notes_dir / f"{today.isoformat()}_ai_tips.md"

    if file_path.exists():
        content = file_path.read_text(encoding="utf-8")
        if "## Q&A ログ" not in content:
            with file_path.open("a", encoding="utf-8") as f:
                f.write("\n## Q&A ログ\n")

    writer.append_qa(qa_entry, target_date=today)


def main() -> None:
    if len(sys.argv) < 2:
        print("使い方: python qa.py \"質問文\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1].strip()
    if not question:
        print("エラー: 質問文が空です。", file=sys.stderr)
        sys.exit(1)

    print("回答を生成中...\n", flush=True)

    agent = QAAgent()
    answer = agent.run(question)

    print(answer)
    print()

    today = date.today()
    writer = ObsidianWriter()
    _ensure_qa_section(writer, today)
    _append_qa_log(writer, answer, today)

    notes_dir = Path(writer._dir)
    file_path = notes_dir / f"{today.isoformat()}_ai_tips.md"
    print(f"[追記完了] {file_path}", flush=True)


if __name__ == "__main__":
    main()

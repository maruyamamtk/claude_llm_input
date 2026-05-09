from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

class TestQAAgent:
    def test_load_context_missing_dir(self, tmp_path):
        """存在しないディレクトリの場合はフォールバックメッセージを返す。"""
        with patch("agent.qa_agent.settings") as mock_settings:
            mock_settings.anthropic_api_key = "dummy"
            mock_settings.obsidian_notes_dir = str(tmp_path / "nonexistent")
            from agent.qa_agent import QAAgent

            agent = QAAgent.__new__(QAAgent)
            agent._notes_dir = tmp_path / "nonexistent"
            context = agent._load_obsidian_context()
            assert "見つかりません" in context

    def test_load_context_reads_up_to_10_files(self, tmp_path):
        """最新10ファイルのみ読み込む。"""
        for i in range(15):
            (tmp_path / f"2026-05-{i+1:02d}_ai_tips.md").write_text(
                f"content {i}", encoding="utf-8"
            )

        with patch("agent.qa_agent.settings") as mock_settings:
            mock_settings.anthropic_api_key = "dummy"
            mock_settings.obsidian_notes_dir = str(tmp_path)
            from agent.qa_agent import QAAgent

            agent = QAAgent.__new__(QAAgent)
            agent._notes_dir = tmp_path
            context = agent._load_obsidian_context()

        file_count = context.count("### 2026-")
        assert file_count == 10

    def test_run_returns_formatted_answer(self):
        """run()がMarkdown形式の回答文字列を返す。"""
        with patch("agent.qa_agent.settings") as mock_settings:
            mock_settings.anthropic_api_key = "dummy"
            mock_settings.obsidian_notes_dir = "/tmp/nonexistent"

            from agent.qa_agent import QAAgent

            agent = QAAgent.__new__(QAAgent)
            agent._notes_dir = Path("/tmp/nonexistent")

            mock_graph = MagicMock()
            mock_graph.invoke.return_value = {
                "question": "テスト質問",
                "context": "テストコンテキスト",
                "answer": "**Q**: テスト質問\n**A**: テスト回答\n**参照**: N/A",
            }
            agent.graph = mock_graph

            answer = agent.run("テスト質問")
            assert "**Q**" in answer
            assert "**A**" in answer
            assert "**参照**" in answer

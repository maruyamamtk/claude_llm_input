from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _run_main():
    import main as m
    m.main()


class TestMainSuccess:
    def test_calls_collect_agent_with_today(self, tmp_path):
        mock_result = {"final_report": "# AI Tips\n## 今日のハイライト\n## トピック別まとめ\n## 今日の実践Tips\n"}
        mock_agent_instance = MagicMock()
        mock_agent_instance.graph.invoke.return_value = mock_result

        mock_writer_instance = MagicMock()
        mock_writer_instance.write.return_value = tmp_path / "2026-05-09_ai_tips.md"

        mock_sender_instance = MagicMock()

        with (
            patch("main.CollectAgent", return_value=mock_agent_instance),
            patch("main.ObsidianWriter", return_value=mock_writer_instance),
            patch("main.GmailSender", return_value=mock_sender_instance),
        ):
            _run_main()

        mock_agent_instance.graph.invoke.assert_called_once()
        call_kwargs = mock_agent_instance.graph.invoke.call_args[0][0]
        assert "run_date" in call_kwargs
        assert call_kwargs["run_date"] == date.today()

    def test_saves_report_via_obsidian_writer(self, tmp_path):
        report_text = "# レポート本文"
        mock_result = {"final_report": report_text}
        mock_agent_instance = MagicMock()
        mock_agent_instance.graph.invoke.return_value = mock_result

        mock_writer_instance = MagicMock()
        mock_writer_instance.write.return_value = tmp_path / "2026-05-09_ai_tips.md"

        mock_sender_instance = MagicMock()

        with (
            patch("main.CollectAgent", return_value=mock_agent_instance),
            patch("main.ObsidianWriter", return_value=mock_writer_instance),
            patch("main.GmailSender", return_value=mock_sender_instance),
        ):
            _run_main()

        mock_writer_instance.write.assert_called_once_with(report_text, date.today())

    def test_sends_report_via_gmail(self, tmp_path):
        report_text = "# レポート本文"
        mock_result = {"final_report": report_text}
        mock_agent_instance = MagicMock()
        mock_agent_instance.graph.invoke.return_value = mock_result

        mock_writer_instance = MagicMock()
        mock_writer_instance.write.return_value = tmp_path / "2026-05-09_ai_tips.md"

        mock_sender_instance = MagicMock()

        with (
            patch("main.CollectAgent", return_value=mock_agent_instance),
            patch("main.ObsidianWriter", return_value=mock_writer_instance),
            patch("main.GmailSender", return_value=mock_sender_instance),
        ):
            _run_main()

        mock_sender_instance.send.assert_called_once_with(report_text, date.today())

    def test_logs_completion_to_stdout(self, tmp_path, caplog):
        mock_result = {"final_report": "report"}
        mock_agent_instance = MagicMock()
        mock_agent_instance.graph.invoke.return_value = mock_result

        mock_writer_instance = MagicMock()
        mock_writer_instance.write.return_value = tmp_path / "2026-05-09_ai_tips.md"

        mock_sender_instance = MagicMock()

        with (
            caplog.at_level(logging.INFO),
            patch("main.CollectAgent", return_value=mock_agent_instance),
            patch("main.ObsidianWriter", return_value=mock_writer_instance),
            patch("main.GmailSender", return_value=mock_sender_instance),
        ):
            _run_main()

        assert "AI Tips Collector 開始" in caplog.text
        assert "AI Tips Collector 完了" in caplog.text
        assert "Obsidianファイル保存完了" in caplog.text


    def test_gmail_failure_does_not_exit_and_logs_warning(self, tmp_path, caplog):
        report_text = "# レポート本文"
        mock_result = {"final_report": report_text}
        mock_agent_instance = MagicMock()
        mock_agent_instance.graph.invoke.return_value = mock_result

        mock_writer_instance = MagicMock()
        mock_writer_instance.write.return_value = tmp_path / "2026-05-09_ai_tips.md"

        mock_sender_instance = MagicMock()
        mock_sender_instance.send.side_effect = Exception("Gmail API error")

        with (
            caplog.at_level(logging.WARNING),
            patch("main.CollectAgent", return_value=mock_agent_instance),
            patch("main.ObsidianWriter", return_value=mock_writer_instance),
            patch("main.GmailSender", return_value=mock_sender_instance),
        ):
            _run_main()  # SystemExit が発生しないこと

        assert "Gmail送信に失敗しました" in caplog.text
        mock_writer_instance.write.assert_called_once()  # Obsidian保存は完了済み


class TestMainFailure:
    def test_exits_with_code_1_on_agent_error(self):
        mock_agent_instance = MagicMock()
        mock_agent_instance.graph.invoke.side_effect = RuntimeError("API error")

        with (
            patch("main.CollectAgent", return_value=mock_agent_instance),
            pytest.raises(SystemExit) as exc_info,
        ):
            _run_main()

        assert exc_info.value.code == 1

    def test_prints_traceback_on_error(self, capsys):
        mock_agent_instance = MagicMock()
        mock_agent_instance.graph.invoke.side_effect = ValueError("something went wrong")

        with (
            patch("main.CollectAgent", return_value=mock_agent_instance),
            pytest.raises(SystemExit),
        ):
            _run_main()

        captured = capsys.readouterr()
        assert "ValueError" in captured.err
        assert "something went wrong" in captured.err

    def test_exits_with_code_1_on_writer_error(self, tmp_path):
        mock_result = {"final_report": "report"}
        mock_agent_instance = MagicMock()
        mock_agent_instance.graph.invoke.return_value = mock_result

        mock_writer_instance = MagicMock()
        mock_writer_instance.write.side_effect = IOError("disk full")

        with (
            patch("main.CollectAgent", return_value=mock_agent_instance),
            patch("main.ObsidianWriter", return_value=mock_writer_instance),
            pytest.raises(SystemExit) as exc_info,
        ):
            _run_main()

        assert exc_info.value.code == 1

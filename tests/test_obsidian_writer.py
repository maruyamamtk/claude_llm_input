"""obsidian_writer.py のユニットテスト"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from service.obsidian_writer import ObsidianWriter


@pytest.fixture()
def writer(tmp_path: Path) -> ObsidianWriter:
    return ObsidianWriter(notes_dir=str(tmp_path))


class TestWrite:
    def test_creates_file_with_correct_name(self, writer: ObsidianWriter, tmp_path: Path):
        target = date(2026, 5, 9)
        writer.write("# Report", target)
        assert (tmp_path / "2026-05-09_ai_tips.md").exists()

    def test_file_contains_report_content(self, writer: ObsidianWriter, tmp_path: Path):
        target = date(2026, 5, 9)
        writer.write("# AI Tips\n\nハイライト", target)
        content = (tmp_path / "2026-05-09_ai_tips.md").read_text(encoding="utf-8")
        assert "# AI Tips" in content
        assert "ハイライト" in content

    def test_overwrites_existing_file(self, writer: ObsidianWriter, tmp_path: Path):
        target = date(2026, 5, 9)
        writer.write("初回内容", target)
        writer.write("上書き内容", target)
        content = (tmp_path / "2026-05-09_ai_tips.md").read_text(encoding="utf-8")
        assert content == "上書き内容"
        assert "初回内容" not in content

    def test_returns_path_object(self, writer: ObsidianWriter, tmp_path: Path):
        result = writer.write("content", date(2026, 5, 9))
        assert isinstance(result, Path)
        assert result == tmp_path / "2026-05-09_ai_tips.md"

    def test_creates_directory_if_not_exists(self, tmp_path: Path):
        nested = tmp_path / "deep" / "nested"
        w = ObsidianWriter(notes_dir=str(nested))
        w.write("内容", date(2026, 5, 9))
        assert (nested / "2026-05-09_ai_tips.md").exists()

    def test_uses_today_when_date_not_given(self, writer: ObsidianWriter, tmp_path: Path):
        path = writer.write("内容")
        assert path.name == f"{date.today().isoformat()}_ai_tips.md"


class TestAppendQA:
    def test_appends_to_existing_file(self, writer: ObsidianWriter, tmp_path: Path):
        target = date(2026, 5, 9)
        writer.write("# Report\n", target)
        writer.append_qa("**Q**: 質問\n**A**: 回答", target)
        content = (tmp_path / "2026-05-09_ai_tips.md").read_text(encoding="utf-8")
        assert "# Report" in content
        assert "**Q**: 質問" in content

    def test_creates_file_if_not_exists(self, writer: ObsidianWriter, tmp_path: Path):
        target = date(2026, 5, 9)
        writer.append_qa("**Q**: 質問\n**A**: 回答", target)
        assert (tmp_path / "2026-05-09_ai_tips.md").exists()

    def test_multiple_appends_accumulate(self, writer: ObsidianWriter, tmp_path: Path):
        target = date(2026, 5, 9)
        writer.write("# Report\n", target)
        writer.append_qa("Q1", target)
        writer.append_qa("Q2", target)
        content = (tmp_path / "2026-05-09_ai_tips.md").read_text(encoding="utf-8")
        assert "Q1" in content
        assert "Q2" in content

    def test_uses_today_when_date_not_given(self, writer: ObsidianWriter, tmp_path: Path):
        writer.append_qa("質問エントリ")
        path = tmp_path / f"{date.today().isoformat()}_ai_tips.md"
        assert path.exists()
        assert "質問エントリ" in path.read_text(encoding="utf-8")

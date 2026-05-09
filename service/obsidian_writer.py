from __future__ import annotations

from datetime import date
from pathlib import Path

from settings import settings


class ObsidianWriter:
    def __init__(self, notes_dir: str | None = None) -> None:
        raw = notes_dir or settings.obsidian_notes_dir
        self._dir = Path(raw).expanduser()

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, target_date: date) -> Path:
        return self._dir / f"{target_date.isoformat()}_ai_tips.md"

    def write(self, report: str, target_date: date | None = None) -> Path:
        """レポート文字列を日付付きMarkdownファイルに保存する（同日上書き）。"""
        if target_date is None:
            target_date = date.today()
        self._ensure_dir()
        path = self._file_path(target_date)
        path.write_text(report, encoding="utf-8")
        return path

    def append_qa(self, qa_entry: str, target_date: date | None = None) -> None:
        """Q&Aエントリを当日のMarkdownファイルの末尾に追記する。"""
        if target_date is None:
            target_date = date.today()
        self._ensure_dir()
        path = self._file_path(target_date)
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n{qa_entry}\n")

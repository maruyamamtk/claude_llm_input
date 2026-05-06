from datetime import date

from pydantic import BaseModel, Field

from models.article import Article


class QAEntry(BaseModel):
    question: str = Field(description="ユーザーの質問")
    answer: str = Field(description="エージェントの回答（300字以内）")
    reference_url: str = Field(default="", description="参照ドキュメントURL")


class Report(BaseModel):
    report_date: date = Field(description="レポート対象日（YYYY-MM-DD）")
    highlights: list[str] = Field(
        default_factory=list,
        description="今日のハイライト（3行サマリー）",
    )
    articles: list[Article] = Field(
        default_factory=list,
        description="収集・要約済み記事一覧",
    )
    tips: list[str] = Field(
        default_factory=list,
        description="今日の実践Tips（3〜5項目）",
    )
    qa_log: list[QAEntry] = Field(
        default_factory=list,
        description="当日のQ&Aログ",
    )

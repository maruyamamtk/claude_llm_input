from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Article(BaseModel):
    title: str = Field(description="記事タイトル")
    url: str = Field(description="記事URL")
    source: str = Field(description="情報ソース名（例: anthropic, openai, github）")
    published_at: datetime | None = Field(default=None, description="公開日時")
    raw_content: str = Field(default="", description="スクレイピングした生コンテンツ")
    summary: str = Field(default="", description="日本語要約（最大500字）")
    is_related: bool | None = Field(
        default=None,
        description="生成AI活用・AIコーディングに関連するかどうか（LLM評価後に設定）",
    )
    relevance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="関連度スコア（0.0〜1.0）",
    )
    category: Literal["anthropic", "openai", "github", "blog", "twitter", "other"] = Field(
        default="other",
        description="記事カテゴリ",
    )

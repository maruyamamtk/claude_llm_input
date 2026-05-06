from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CollectorSettings(BaseSettings):
    max_articles_per_source: int = Field(default=10, description="ソースごとの最大収集件数")
    max_retry_loops: int = Field(default=3, description="追加収集の最大ループ回数")
    summary_max_chars: int = Field(default=500, description="記事要約の最大文字数")
    filter_min_score: float = Field(default=0.6, description="関連度フィルタリングの最低スコア")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = Field(description="Anthropic API キー")
    github_token: str = Field(default="", description="GitHub Personal Access Token（レート制限緩和用）")
    gmail_credentials_path: str = Field(
        default="credentials.json",
        description="Gmail API OAuth2 認証情報ファイルパス",
    )
    obsidian_notes_dir: str = Field(
        default="~/Desktop/obsidian_note/08_AINews",
        description="Obsidianノートの保存先ディレクトリ",
    )
    collector: CollectorSettings = Field(default_factory=CollectorSettings)


settings = Settings()

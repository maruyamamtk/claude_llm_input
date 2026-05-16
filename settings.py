from __future__ import annotations

import logging
import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _bootstrap_from_secret_manager() -> None:
    """Cloud Run環境でSecret Managerからシークレットを環境変数に事前ロードする。

    GCP_PROJECT_IDが設定されている場合のみ実行される。
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        return

    try:
        from google.cloud import secretmanager  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("google-cloud-secret-manager がインストールされていません。Secret Managerをスキップします。")
        return

    client = secretmanager.SecretManagerServiceClient()
    secret_map = {
        "google-api-key": "GOOGLE_API_KEY",
        "github-token": "GITHUB_TOKEN",
    }
    for secret_id, env_var in secret_map.items():
        if env_var in os.environ:
            continue
        try:
            name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            os.environ[env_var] = response.payload.data.decode("utf-8")
            logger.info("Secret Manager からロード完了: %s -> %s", secret_id, env_var)
        except Exception as exc:
            logger.error("Secret Manager からのロード失敗: %s (%s)", secret_id, exc)


_bootstrap_from_secret_manager()


class CollectorSettings(BaseSettings):
    max_articles_per_source: int = Field(default=10, description="ソースごとの最大収集件数")
    max_retry_loops: int = Field(default=3, description="追加収集の最大ループ回数")
    summary_max_chars: int = Field(default=500, description="記事要約の最大文字数")
    filter_min_score: float = Field(default=0.6, description="関連度フィルタリングの最低スコア")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    google_api_key: str = Field(description="Google AI API キー")
    github_token: str = Field(default="", description="GitHub Personal Access Token（レート制限緩和用）")
    gmail_credentials_path: str = Field(
        default="credentials.json",
        description="Gmail API OAuth2 認証情報ファイルパス",
    )
    gmail_token_path: str = Field(
        default="token.json",
        description="Gmail API OAuth2 トークンキャッシュファイルパス",
    )
    gmail_sender_address: str = Field(
        default="marumaru5922@gmail.com",
        description="Gmail送信元・送信先アドレス",
    )
    obsidian_notes_dir: str = Field(
        default="~/Desktop/obsidian_note/08_AINews",
        description="Obsidianノートの保存先ディレクトリ",
    )
    collector: CollectorSettings = Field(default_factory=CollectorSettings)


settings = Settings()

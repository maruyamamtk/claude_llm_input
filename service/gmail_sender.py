from __future__ import annotations

import base64
import json
import logging
import os
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import markdown
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from settings import settings

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class GmailSender:
    def __init__(
        self,
        credentials_path: str | None = None,
        token_path: str | None = None,
        sender_address: str | None = None,
    ) -> None:
        self._credentials_path = Path(credentials_path or settings.gmail_credentials_path)
        self._token_path = Path(token_path or settings.gmail_token_path)
        self._address = sender_address or settings.gmail_sender_address

    def _load_credentials_from_secret_manager(self, project_id: str) -> Credentials:
        """Secret Manager の gmail-token シークレットから認証情報を取得する。"""
        from google.cloud import secretmanager  # type: ignore[import-untyped]

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/gmail-token/versions/latest"
        response = client.access_secret_version(request={"name": name})
        token_data = json.loads(response.payload.data.decode("utf-8"))
        creds = Credentials.from_authorized_user_info(token_data, _SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds

    def _get_credentials(self) -> Credentials:
        # Cloud Run環境ではSecret ManagerからGmailトークンを読み込む
        project_id = os.environ.get("GCP_PROJECT_ID")
        if project_id:
            logger.info("Secret Manager から Gmail トークンを読み込みます (project=%s)", project_id)
            return self._load_credentials_from_secret_manager(project_id)

        # ローカル環境ではファイルから読み込む
        creds: Credentials | None = None

        if self._token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self._token_path), _SCOPES)

        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # valid=False かつ expired=False（トークン破損など）も含め再認証する
            # 注意: run_local_server はブラウザが必要なため、初回はGUI環境での実行が必要
            if not self._credentials_path.exists():
                raise FileNotFoundError(
                    f"Gmail認証情報ファイルが見つかりません: {self._credentials_path}\n"
                    "GCPコンソールでOAuth2クライアント（デスクトップアプリ）を作成し、"
                    "credentials.jsonをダウンロードしてください。\n"
                    "初回認証はブラウザが利用できるGUI環境で実行してください。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self._credentials_path), _SCOPES
            )
            creds = flow.run_local_server(port=0)

        self._token_path.write_text(creds.to_json(), encoding="utf-8")
        self._token_path.chmod(0o600)
        logger.info("Gmail認証トークンを保存しました: %s", self._token_path)
        return creds

    def _build_message(self, report: str, target_date: date) -> dict:
        subject = f"[AI Tips] {target_date.isoformat()} の注目情報"
        html_body = markdown.markdown(report, extensions=["extra", "nl2br"])

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._address
        msg["To"] = self._address
        msg.attach(MIMEText(report, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        return {"raw": raw}

    def send(self, report: str, target_date: date) -> None:
        """レポートをHTMLメールとしてGmailで送信する。"""
        creds = self._get_credentials()
        service = build("gmail", "v1", credentials=creds)
        message = self._build_message(report, target_date)
        service.users().messages().send(userId="me", body=message).execute()
        logger.info(
            "Gmailメール送信完了: 宛先=%s, 件名=[AI Tips] %s の注目情報",
            self._address,
            target_date.isoformat(),
        )

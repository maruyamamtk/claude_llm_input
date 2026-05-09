from __future__ import annotations

import base64
from datetime import date
from email import message_from_bytes
from email.header import decode_header as _decode_header
from unittest.mock import MagicMock, patch

import pytest

from service.gmail_sender import GmailSender


class TestGmailSenderBuildMessage:
    def test_subject_format(self, tmp_path):
        sender = GmailSender(
            credentials_path=str(tmp_path / "creds.json"),
            token_path=str(tmp_path / "token.json"),
            sender_address="test@gmail.com",
        )
        target_date = date(2026, 5, 9)
        msg_dict = sender._build_message("# Hello", target_date)

        raw_bytes = base64.urlsafe_b64decode(msg_dict["raw"])
        msg = message_from_bytes(raw_bytes)
        decoded_parts = _decode_header(msg["Subject"])
        subject = "".join(
            part.decode(enc or "utf-8") if isinstance(part, bytes) else part
            for part, enc in decoded_parts
        )
        assert subject == "[AI Tips] 2026-05-09 の注目情報"

    def test_from_and_to_set_correctly(self, tmp_path):
        sender = GmailSender(
            credentials_path=str(tmp_path / "creds.json"),
            token_path=str(tmp_path / "token.json"),
            sender_address="user@example.com",
        )
        msg_dict = sender._build_message("report", date(2026, 5, 9))
        raw_bytes = base64.urlsafe_b64decode(msg_dict["raw"])
        msg = message_from_bytes(raw_bytes)
        assert msg["From"] == "user@example.com"
        assert msg["To"] == "user@example.com"

    def test_message_has_both_plain_and_html_parts(self, tmp_path):
        sender = GmailSender(
            credentials_path=str(tmp_path / "creds.json"),
            token_path=str(tmp_path / "token.json"),
            sender_address="test@gmail.com",
        )
        msg_dict = sender._build_message("# Hello **World**", date(2026, 5, 9))
        raw_bytes = base64.urlsafe_b64decode(msg_dict["raw"])
        msg = message_from_bytes(raw_bytes)

        content_types = [part.get_content_type() for part in msg.walk()]
        assert "text/plain" in content_types
        assert "text/html" in content_types

    def test_html_part_contains_converted_markdown(self, tmp_path):
        sender = GmailSender(
            credentials_path=str(tmp_path / "creds.json"),
            token_path=str(tmp_path / "token.json"),
            sender_address="test@gmail.com",
        )
        msg_dict = sender._build_message("# Hello **World**", date(2026, 5, 9))
        raw_bytes = base64.urlsafe_b64decode(msg_dict["raw"])
        msg = message_from_bytes(raw_bytes)

        html_part = next(p for p in msg.walk() if p.get_content_type() == "text/html")
        html_content = html_part.get_payload(decode=True).decode("utf-8")
        assert "<h1>" in html_content
        assert "<strong>" in html_content


class TestGmailSenderGetCredentials:
    def test_raises_when_credentials_file_missing(self, tmp_path):
        sender = GmailSender(
            credentials_path=str(tmp_path / "nonexistent.json"),
            token_path=str(tmp_path / "token.json"),
            sender_address="test@gmail.com",
        )
        with pytest.raises(FileNotFoundError, match="Gmail認証情報ファイルが見つかりません"):
            sender._get_credentials()

    def test_uses_cached_token_when_valid(self, tmp_path):
        token_file = tmp_path / "token.json"

        mock_creds = MagicMock()
        mock_creds.valid = True

        with patch("service.gmail_sender.Credentials.from_authorized_user_file", return_value=mock_creds):
            token_file.write_text("{}", encoding="utf-8")
            sender = GmailSender(
                credentials_path=str(tmp_path / "creds.json"),
                token_path=str(token_file),
                sender_address="test@gmail.com",
            )
            result = sender._get_credentials()

        assert result is mock_creds

    def test_refreshes_expired_token(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text("{}", encoding="utf-8")

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_token_value"
        mock_creds.to_json.return_value = "{}"

        with patch("service.gmail_sender.Credentials.from_authorized_user_file", return_value=mock_creds):
            sender = GmailSender(
                credentials_path=str(tmp_path / "creds.json"),
                token_path=str(token_file),
                sender_address="test@gmail.com",
            )
            result = sender._get_credentials()

        mock_creds.refresh.assert_called_once()
        assert result is mock_creds


class TestGmailSenderSend:
    def test_send_calls_gmail_api(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text("{}", encoding="utf-8")

        mock_creds = MagicMock()
        mock_creds.valid = True

        mock_service = MagicMock()
        mock_messages = mock_service.users.return_value.messages.return_value
        mock_messages.send.return_value.execute.return_value = {"id": "abc123"}

        sender = GmailSender(
            credentials_path=str(tmp_path / "creds.json"),
            token_path=str(token_file),
            sender_address="test@gmail.com",
        )

        with (
            patch("service.gmail_sender.Credentials.from_authorized_user_file", return_value=mock_creds),
            patch("service.gmail_sender.build", return_value=mock_service),
        ):
            sender.send("# Report", date(2026, 5, 9))

        mock_messages.send.assert_called_once()
        call_kwargs = mock_messages.send.call_args[1]
        assert call_kwargs["userId"] == "me"
        assert "raw" in call_kwargs["body"]

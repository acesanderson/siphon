from __future__ import annotations

import base64
import email
import os
from pathlib import Path
from typing import override

from siphon_api.enums import SourceType
from siphon_api.interfaces import ExtractorStrategy
from siphon_api.models import ContentData
from siphon_api.models import SourceInfo

_DEFAULT_TOKEN = Path.home() / ".config" / "siphon" / "gmail_token.json"
_DEFAULT_SECRET = Path.home() / ".config" / "siphon" / "gmail_client_secret.json"
_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class EmailExtractor(ExtractorStrategy):
    """Fetch and decode a Gmail message by ID."""

    source_type: SourceType = SourceType.EMAIL

    @override
    def extract(self, source: SourceInfo) -> ContentData:
        message_id = source.uri.removeprefix("email:///gmail/")
        service = self._get_service()
        msg = service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

        body = self._extract_body(msg)
        metadata = self._extract_metadata(msg)
        return ContentData(
            source_type=self.source_type,
            text=body,
            metadata=metadata,
        )

    def _get_service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        token_path = Path(os.environ.get("GMAIL_TOKEN_FILE", str(_DEFAULT_TOKEN)))
        secret_path = Path(os.environ.get("GMAIL_CLIENT_SECRET_FILE", str(_DEFAULT_SECRET)))

        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), _SCOPES)
                creds = flow.run_local_server()
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json())
        return build("gmail", "v1", credentials=creds)

    def _extract_body(self, msg: dict) -> str:
        payload = msg.get("payload", {})
        return self._walk_parts(payload)

    def _walk_parts(self, payload: dict) -> str:
        mime = payload.get("mimeType", "")
        if mime == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        for part in payload.get("parts", []):
            text = self._walk_parts(part)
            if text:
                return text
        return ""

    def _extract_metadata(self, msg: dict) -> dict:
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        return {
            "message_id": msg.get("id", ""),
            "thread_id": msg.get("threadId", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "subject": headers.get("subject", ""),
            "date": headers.get("date", ""),
        }

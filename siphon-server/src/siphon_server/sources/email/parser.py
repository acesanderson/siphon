from __future__ import annotations

import hashlib
import re
from typing import override

from siphon_api.enums import SourceType
from siphon_api.interfaces import ParserStrategy
from siphon_api.models import SourceInfo

_MSG_ID_RE = re.compile(r"[0-9a-f]{16}$")
_GMAIL_URL_RE = re.compile(r"mail\.google\.com.*[/#]([0-9a-f]{16})")


class EmailParser(ParserStrategy):
    """Parse Gmail sources: message URLs or bare message IDs."""

    source_type: SourceType = SourceType.EMAIL

    @override
    def can_handle(self, source: str) -> bool:
        if _GMAIL_URL_RE.search(source):
            return True
        if _MSG_ID_RE.match(source):
            return True
        return False

    @override
    def parse(self, source: str) -> SourceInfo:
        message_id = self._extract_id(source)
        uri = f"email:///gmail/{message_id}"
        h = hashlib.sha256(message_id.encode()).hexdigest()[:16]
        return SourceInfo(
            source_type=self.source_type,
            uri=uri,
            original_source=source,
            hash=h,
        )

    def _extract_id(self, source: str) -> str:
        m = _GMAIL_URL_RE.search(source)
        if m:
            return m.group(1)
        return source.strip()

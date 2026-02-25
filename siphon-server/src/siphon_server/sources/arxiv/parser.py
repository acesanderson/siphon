from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING
from typing import override

from siphon_api.enums import SourceType
from siphon_api.interfaces import ParserStrategy
from siphon_api.models import SourceInfo

_BARE_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")
_URL_ID_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})")


class ArxivParser(ParserStrategy):
    """Parse arXiv sources: bare IDs or arxiv.org URLs."""

    source_type: SourceType = SourceType.ARXIV

    @override
    def can_handle(self, source: str) -> bool:
        source = source.strip()
        if _BARE_ID_RE.match(source):
            return True
        if _URL_ID_RE.search(source):
            return True
        return False

    @override
    def parse(self, source: str) -> SourceInfo:
        arxiv_id = self._extract_id(source.strip())
        uri = f"arxiv:///{arxiv_id}"
        h = hashlib.sha256(arxiv_id.encode()).hexdigest()[:16]
        return SourceInfo(
            source_type=self.source_type,
            uri=uri,
            original_source=source,
            hash=h,
        )

    def _extract_id(self, source: str) -> str:
        m = _URL_ID_RE.search(source)
        if m:
            return m.group(1)
        # strip version suffix from bare ID
        return _BARE_ID_RE.match(source).group(0).split("v")[0]

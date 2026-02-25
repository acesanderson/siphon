from __future__ import annotations

import hashlib
import re
from typing import override

from siphon_api.enums import SourceType
from siphon_api.interfaces import ParserStrategy
from siphon_api.models import SourceInfo

_GITHUB_RE = re.compile(
    r"github\.com/([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+?)(?:\.git)?(?:/.*)?$"
)


class GitHubParser(ParserStrategy):
    """Parse GitHub repository URLs."""

    source_type: SourceType = SourceType.GITHUB

    @override
    def can_handle(self, source: str) -> bool:
        m = _GITHUB_RE.search(source)
        if not m:
            return False
        # Must have both owner and repo segments
        return bool(m.group(1)) and bool(m.group(2))

    @override
    def parse(self, source: str) -> SourceInfo:
        m = _GITHUB_RE.search(source)
        assert m, f"Not a valid GitHub URL: {source}"
        owner = m.group(1)
        repo = m.group(2)
        uri = f"github:///{owner}/{repo}"
        h = hashlib.sha256(f"{owner}/{repo}".encode()).hexdigest()[:16]
        return SourceInfo(
            source_type=self.source_type,
            uri=uri,
            original_source=source,
            hash=h,
        )

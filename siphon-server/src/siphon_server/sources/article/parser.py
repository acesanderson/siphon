from __future__ import annotations
from siphon_api.interfaces import ParserStrategy
from siphon_api.models import SourceInfo
from siphon_api.enums import SourceType
from typing import override
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import idna
import posixpath
import hashlib

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "mc_eid",
    "mc_cid",
    "vero_conv",
    "vero_id",
    "igshid",
}


class ArticleParser(ParserStrategy):
    """
    Parse Article sources.
    """

    source_type: SourceType = SourceType.ARTICLE

    @override
    def can_handle(self, source: str) -> bool:
        """
        Needs to be:
        - a url
        - NOT from youtube.com or youtu.be
        - NOT a google drive / docs / sheets link
        """
        return (source.startswith("http://") or source.startswith("https://")) and all(
            domain not in source
            for domain in [
                "youtube.com",
                "youtu.be",
                "drive.google.com",
                "docs.google.com",
                "sheets.google.com",
                "mail.google.com",
                "github.com",
                "arxiv.org",
            ]
        )

    @override
    def parse(self, source: str) -> SourceInfo:
        """
        Parse Article URL into SourceInfo
        source_type: SourceType
        uri: str  # Canonical identifier (e.g., "article:///
        original_source: str  # User input (e.g., "https://techcrunch.com/...")
        hash: str | None = None
        """

        hash = self._article_key(source)
        original_source = self._normalize_url(source)
        uri = "article:///sha256/" + hash

        return SourceInfo(
            source_type=self.source_type,
            uri=uri,
            original_source=original_source,
            hash=hash,
        )

    def _normalize_url(self, url: str) -> str:
        """
        Normalize a URL by:
        - Lowercasing scheme and host
        - IDNA / punycode encoding of host
        - Dropping default ports
        - Dot-segment removal
        - Normalizing and filtering query parameters
        - Removing fragment
        Args:
            url (str): The URL to normalize.
        Returns:
            str: The normalized URL.
        """
        s = urlsplit(url)
        scheme = s.scheme.lower()
        host = s.hostname.lower() if s.hostname else ""
        # IDNA / punycode
        if host:
            host = idna.encode(host).decode("ascii")

        # Drop default ports
        netloc = host
        if s.port and not (
            (scheme == "http" and s.port == 80) or (scheme == "https" and s.port == 443)
        ):
            netloc = f"{host}:{s.port}"
        if s.username or s.password:
            userinfo = s.username or ""
            if s.password:
                userinfo += f":{s.password}"
            netloc = f"{userinfo}@{netloc}"

        # Dot-segment removal
        segments = [seg for seg in s.path.split("/") if seg not in (".", "")]
        path = (
            "/" + "/".join(posixpath.normpath("/" + "/".join(segments)).split("/")[1:])
            if s.path
            else ""
        )

        # Normalize & filter query params
        q = [(k, v) for k, v in parse_qsl(s.query, keep_blank_values=True)]
        q = [(k, v) for k, v in q if k not in TRACKING_PARAMS]
        q.sort()
        query = urlencode(q, doseq=True)

        # Remove fragment
        return urlunsplit((scheme, netloc, path, query, ""))

    def _article_key(self, url: str) -> str:
        """
        Generate a unique key for an article based on its normalized URL.
        """
        norm = self._normalize_url(url)
        h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        return h

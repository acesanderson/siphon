from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET
from typing import override

from siphon_api.enums import SourceType
from siphon_api.interfaces import ExtractorStrategy
from siphon_api.models import ContentData
from siphon_api.models import SourceInfo

_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_NS = "http://arxiv.org/schemas/atom"


class ArxivExtractor(ExtractorStrategy):
    """Fetch abstract and metadata from the arXiv Atom API."""

    source_type: SourceType = SourceType.ARXIV

    @override
    def extract(self, source: SourceInfo) -> ContentData:
        arxiv_id = source.uri.removeprefix("arxiv:///")
        url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
        with urllib.request.urlopen(url) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        entry = root.find(f"{{{_ATOM_NS}}}entry")
        assert entry is not None, f"No entry found for {arxiv_id}"

        abstract = (entry.findtext(f"{{{_ATOM_NS}}}summary") or "").strip()
        title = (entry.findtext(f"{{{_ATOM_NS}}}title") or "").strip()
        published = entry.findtext(f"{{{_ATOM_NS}}}published") or ""
        authors = [
            a.findtext(f"{{{_ATOM_NS}}}name") or ""
            for a in entry.findall(f"{{{_ATOM_NS}}}author")
        ]
        categories = [
            t.get("term", "")
            for t in entry.findall(f"{{{_ATOM_NS}}}category")
        ]
        pdf_url = ""
        for link in entry.findall(f"{{{_ATOM_NS}}}link"):
            if link.get("title") == "pdf":
                pdf_url = link.get("href", "")
                break

        metadata: dict = {
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors,
            "categories": categories,
            "published": published,
            "pdf_url": pdf_url,
        }
        return ContentData(
            source_type=self.source_type,
            text=abstract,
            metadata=metadata,
        )

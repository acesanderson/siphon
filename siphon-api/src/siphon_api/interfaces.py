from typing import Protocol, Awaitable
from siphon_api.models import SourceInfo, ContentData, EnrichedData
from siphon_api.enums import SourceType


class ParserStrategy(Protocol):
    """
    Interface for source parsing strategies
    """

    source_type: SourceType

    def can_handle(self, source: str) -> bool: ...

    def parse(self, source: str) -> SourceInfo: ...


class ExtractorStrategy(Protocol):
    """
    Interface for content extraction strategies
    """

    source_type: SourceType

    def extract(self, source: SourceInfo) -> ContentData: ...


class EnricherStrategy(Protocol):
    """
    Interface for content enrichment strategies.
    (summarization approaches will differ for different content types)
    Note: this takes an optional preferred_model parameter to allow for model selection.
    """

    source_type: SourceType

    def enrich(self, content: ContentData, preferred_model: str) -> Awaitable[EnrichedData]: ...

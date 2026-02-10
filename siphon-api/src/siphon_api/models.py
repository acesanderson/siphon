from pydantic import BaseModel, Field
from siphon_api.enums import SourceType
from typing import Any, Literal


class SourceInfo(BaseModel):
    """
    Parsed source metadata. Replaces all URI subclasses.
    """

    kind: Literal["SourceInfo"] = "SourceInfo"  # Discriminator

    source_type: SourceType
    uri: str  # Canonical identifier (e.g., "youtube:///dQw4w9WgXcQ")
    original_source: str  # User input (e.g., "https://youtube.com/watch?v=dQw4w9WgXcQ")
    hash: str | None = None


class ContentData(BaseModel):
    """
    Extracted content. Replaces all Context subclasses.
    """

    kind: Literal["ContentData"] = "ContentData"  # Discriminator

    source_type: SourceType
    text: str  # The actual content (transcript, article text, file contents)
    metadata: dict[str, Any] = Field(default_factory=dict)

    token_count: int | None = (
        None  # Optional token count (specifically requested as an ActionType in pipeline)
    )


class EnrichedData(BaseModel):
    """
    AI-generated enrichments. Replaces all SyntheticData subclasses.
    """

    kind: Literal["EnrichedData"] = "EnrichedData"  # Discriminator

    source_type: SourceType
    title: str = ""
    description: str = ""
    summary: str = ""
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class ProcessedContent(BaseModel):
    """
    Final aggregate - main output of Siphon pipeline.
    """

    kind: Literal["ProcessedContent"] = "ProcessedContent"  # Discriminator

    source: SourceInfo
    content: ContentData
    enrichment: EnrichedData
    tags: list[str] = Field(default_factory=list)
    created_at: int
    updated_at: int

    # Convenience properties
    @property
    def source_type(self) -> SourceType:
        return self.source.source_type

    @property
    def uri(self) -> str:
        return self.source.uri

    @property
    def text(self) -> str:
        return self.content.text

    @property
    def metadata(self) -> dict[str, Any]:
        return self.content.metadata

    @property
    def title(self) -> str:
        return self.enrichment.title

    @property
    def description(self) -> str:
        return self.enrichment.description

    @property
    def summary(self) -> str:
        return self.enrichment.summary


PipelineClass = (
    ProcessedContent | ContentData | EnrichedData | SourceInfo
)  # Hence our discriminator field 'kind'


class QueryResultItem(BaseModel):
    """
    Lightweight result metadata for query history display.
    Contains just enough information to render a table row.
    """
    uri: str
    title: str
    source_type: str
    created_at: int


class QueryHistory(BaseModel):
    """
    Query execution history record.

    Stores query parameters and results for CLI recall functionality
    (like terminal arrow-up). Enables `siphon results --history` and
    `siphon results --get <id>`.
    """

    kind: Literal["QueryHistory"] = "QueryHistory"  # Discriminator

    id: int | None = None  # None for new records, set after DB insert
    query_string: str = ""
    source_type: str | None = None
    extension: str | None = None
    executed_at: int
    results: list[QueryResultItem] = Field(default_factory=list)

    @property
    def result_count(self) -> int:
        """Number of results in this query."""
        return len(self.results)

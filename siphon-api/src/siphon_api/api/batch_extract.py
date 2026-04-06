from __future__ import annotations

from pydantic import BaseModel
from pydantic import Field


class BatchExtractRequest(BaseModel):
    sources: list[str] = Field(..., description="List of source strings to extract.")
    max_concurrent: int = Field(
        default=10,
        ge=1,
        description="Maximum number of concurrent extractions.",
    )


class BatchExtractResult(BaseModel):
    source: str
    text: str | None = None
    error: str | None = None


class BatchExtractResponse(BaseModel):
    results: list[BatchExtractResult]

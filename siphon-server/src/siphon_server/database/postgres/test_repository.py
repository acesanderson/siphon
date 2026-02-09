"""Tests for ContentRepository query methods."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from siphon_api.enums import SourceType
from siphon_api.models import (
    ContentData,
    EnrichedData,
    ProcessedContent,
    SourceInfo,
)
from siphon_server.database.postgres.repository import ContentRepository


@pytest.fixture
def repository() -> ContentRepository:
    """Create a ContentRepository instance for testing."""
    return ContentRepository()


@pytest.fixture
def sample_youtube_content() -> ProcessedContent:
    """Create sample YouTube ProcessedContent."""
    return ProcessedContent(
        source=SourceInfo(
            source_type=SourceType.YOUTUBE,
            uri="youtube:///dQw4w9WgXcQ",
            original_source="https://youtube.com/watch?v=dQw4w9WgXcQ",
        ),
        content=ContentData(
            source_type=SourceType.YOUTUBE,
            text="Never gonna give you up, never gonna let you down",
            metadata={"duration": 213},
        ),
        enrichment=EnrichedData(
            source_type=SourceType.YOUTUBE,
            title="Rick Astley - Never Gonna Give You Up",
            description="Official music video for the 1987 hit song",
            summary="Rick Astley performs his classic 80s song about commitment",
        ),
        created_at=int(datetime(2024, 1, 15, tzinfo=timezone.utc).timestamp()),
        updated_at=int(datetime(2024, 1, 15, tzinfo=timezone.utc).timestamp()),
    )


@pytest.fixture
def sample_article_content() -> ProcessedContent:
    """Create sample Article ProcessedContent."""
    return ProcessedContent(
        source=SourceInfo(
            source_type=SourceType.ARTICLE,
            uri="article:///abc123",
            original_source="https://example.com/article",
        ),
        content=ContentData(
            source_type=SourceType.ARTICLE,
            text="Machine learning is transforming AI development",
            metadata={},
        ),
        enrichment=EnrichedData(
            source_type=SourceType.ARTICLE,
            title="The Future of AI and Machine Learning",
            description="An exploration of modern AI techniques",
            summary="Article discusses recent advances in machine learning",
        ),
        created_at=int(datetime(2024, 2, 1, tzinfo=timezone.utc).timestamp()),
        updated_at=int(datetime(2024, 2, 1, tzinfo=timezone.utc).timestamp()),
    )


def test_search_by_text_finds_match_in_title(
    repository: ContentRepository,
    sample_youtube_content: ProcessedContent,
) -> None:
    """search_by_text should find content when query matches title."""
    # Store content
    repository.set(sample_youtube_content)

    # Search for text in title
    results = repository.search_by_text(query="Rick Astley", limit=10)

    assert len(results) >= 1
    assert any(pc.uri == sample_youtube_content.uri for pc in results)


def test_search_by_text_finds_match_in_description(
    repository: ContentRepository,
    sample_article_content: ProcessedContent,
) -> None:
    """search_by_text should find content when query matches description."""
    # Store content
    repository.set(sample_article_content)

    # Search for text in description
    results = repository.search_by_text(query="modern AI techniques", limit=10)

    assert len(results) >= 1
    assert any(pc.uri == sample_article_content.uri for pc in results)


def test_search_by_text_is_case_insensitive(
    repository: ContentRepository,
    sample_youtube_content: ProcessedContent,
) -> None:
    """search_by_text should be case-insensitive."""
    repository.set(sample_youtube_content)

    # Search with different cases
    results_lower = repository.search_by_text(query="rick astley", limit=10)
    results_upper = repository.search_by_text(query="RICK ASTLEY", limit=10)

    assert len(results_lower) >= 1
    assert len(results_upper) >= 1


def test_search_by_text_filters_by_source_type(
    repository: ContentRepository,
    sample_youtube_content: ProcessedContent,
    sample_article_content: ProcessedContent,
) -> None:
    """search_by_text should filter by source_type when provided."""
    repository.set(sample_youtube_content)
    repository.set(sample_article_content)

    # Search only for YouTube content
    results = repository.search_by_text(
        query="",  # Empty query matches all
        source_type=SourceType.YOUTUBE,
        limit=10,
    )

    assert all(pc.source_type == SourceType.YOUTUBE for pc in results)


def test_search_by_text_filters_by_date_greater_than(
    repository: ContentRepository,
    sample_youtube_content: ProcessedContent,
    sample_article_content: ProcessedContent,
) -> None:
    """search_by_text should filter by date with > operator."""
    repository.set(sample_youtube_content)  # 2024-01-15
    repository.set(sample_article_content)  # 2024-02-01

    # Search for content after 2024-01-20
    cutoff = datetime(2024, 1, 20, tzinfo=timezone.utc)
    results = repository.search_by_text(
        query="",
        date_filter=(">", cutoff),
        limit=10,
    )

    # Should only find article (2024-02-01), not YouTube (2024-01-15)
    assert all(
        pc.created_at > int(cutoff.timestamp()) for pc in results
    )


def test_search_by_text_filters_by_date_less_than(
    repository: ContentRepository,
    sample_youtube_content: ProcessedContent,
    sample_article_content: ProcessedContent,
) -> None:
    """search_by_text should filter by date with < operator."""
    repository.set(sample_youtube_content)  # 2024-01-15
    repository.set(sample_article_content)  # 2024-02-01

    # Search for content before 2024-01-20
    cutoff = datetime(2024, 1, 20, tzinfo=timezone.utc)
    results = repository.search_by_text(
        query="",
        date_filter=("<", cutoff),
        limit=10,
    )

    # Should only find YouTube (2024-01-15), not article (2024-02-01)
    assert all(
        pc.created_at < int(cutoff.timestamp()) for pc in results
    )


def test_search_by_text_respects_limit(
    repository: ContentRepository,
) -> None:
    """search_by_text should respect the limit parameter."""
    # Create multiple content items
    for i in range(20):
        content = ProcessedContent(
            source=SourceInfo(
                source_type=SourceType.ARTICLE,
                uri=f"article:///{i}",
                original_source=f"https://example.com/{i}",
            ),
            content=ContentData(
                source_type=SourceType.ARTICLE,
                text=f"Article {i}",
                metadata={},
            ),
            enrichment=EnrichedData(
                source_type=SourceType.ARTICLE,
                title=f"Test Article {i}",
                description="Test description",
                summary="Test summary",
            ),
            created_at=int(datetime.now(timezone.utc).timestamp()),
            updated_at=int(datetime.now(timezone.utc).timestamp()),
        )
        repository.set(content)

    results = repository.search_by_text(query="Test", limit=5)
    assert len(results) <= 5


def test_search_by_text_returns_empty_list_when_no_matches(
    repository: ContentRepository,
) -> None:
    """search_by_text should return empty list when no matches found."""
    results = repository.search_by_text(
        query="nonexistent query that matches nothing",
        limit=10,
    )
    assert results == []


def test_list_all_returns_all_content_sorted_by_date(
    repository: ContentRepository,
    sample_youtube_content: ProcessedContent,
    sample_article_content: ProcessedContent,
) -> None:
    """list_all should return all content sorted by created_at descending."""
    repository.set(sample_youtube_content)  # 2024-01-15
    repository.set(sample_article_content)  # 2024-02-01

    results = repository.list_all(limit=10)

    assert len(results) >= 2
    # Should be sorted by date descending (newest first)
    for i in range(len(results) - 1):
        assert results[i].created_at >= results[i + 1].created_at


def test_list_all_filters_by_source_type(
    repository: ContentRepository,
    sample_youtube_content: ProcessedContent,
    sample_article_content: ProcessedContent,
) -> None:
    """list_all should filter by source_type when provided."""
    repository.set(sample_youtube_content)
    repository.set(sample_article_content)

    results = repository.list_all(source_type=SourceType.YOUTUBE, limit=10)

    assert all(pc.source_type == SourceType.YOUTUBE for pc in results)


def test_list_all_respects_limit(
    repository: ContentRepository,
) -> None:
    """list_all should respect the limit parameter."""
    # Create multiple content items
    for i in range(15):
        content = ProcessedContent(
            source=SourceInfo(
                source_type=SourceType.ARTICLE,
                uri=f"article:///list{i}",
                original_source=f"https://example.com/list{i}",
            ),
            content=ContentData(
                source_type=SourceType.ARTICLE,
                text=f"Content {i}",
                metadata={},
            ),
            enrichment=EnrichedData(
                source_type=SourceType.ARTICLE,
                title=f"Title {i}",
                description="Description",
                summary="Summary",
            ),
            created_at=int(datetime.now(timezone.utc).timestamp()),
            updated_at=int(datetime.now(timezone.utc).timestamp()),
        )
        repository.set(content)

    results = repository.list_all(limit=5)
    assert len(results) <= 5

"""Tests for SiphonClient."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from siphon_api.enums import SourceType
from siphon_api.models import (
    ContentData,
    EnrichedData,
    ProcessedContent,
    SourceInfo,
)
from siphon_client.client import SiphonClient
from siphon_client.collections.collection import Collection


@pytest.fixture
def mock_repository() -> MagicMock:
    """Create a mock ContentRepository."""
    return MagicMock()


@pytest.fixture
def client(mock_repository: MagicMock) -> SiphonClient:
    """Create a SiphonClient with mocked repository."""
    with patch("siphon_client.client.ContentRepository", return_value=mock_repository):
        return SiphonClient()


@pytest.fixture
def sample_content() -> ProcessedContent:
    """Create sample ProcessedContent for testing."""
    return ProcessedContent(
        source=SourceInfo(
            source_type=SourceType.YOUTUBE,
            uri="youtube:///test123",
            original_source="https://youtube.com/watch?v=test123",
        ),
        content=ContentData(
            source_type=SourceType.YOUTUBE,
            text="Test content",
            metadata={},
        ),
        enrichment=EnrichedData(
            source_type=SourceType.YOUTUBE,
            title="Test Title",
            description="Test description",
            summary="Test summary",
        ),
        created_at=int(datetime.now(timezone.utc).timestamp()),
        updated_at=int(datetime.now(timezone.utc).timestamp()),
    )


def test_search_calls_repository_search_by_text(
    client: SiphonClient,
    mock_repository: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """search should call repository.search_by_text with correct parameters."""
    mock_repository.search_by_text.return_value = [sample_content]

    result = client.search(
        query="test query",
        mode="sql",
        source_type=SourceType.YOUTUBE,
        limit=5,
    )

    mock_repository.search_by_text.assert_called_once_with(
        query="test query",
        source_type=SourceType.YOUTUBE,
        date_filter=None,
        limit=5,
    )
    assert isinstance(result, Collection)
    assert result.count() == 1


def test_search_with_semantic_mode_raises_not_implemented(
    client: SiphonClient,
) -> None:
    """search with mode='semantic' should raise NotImplementedError."""
    with pytest.raises(NotImplementedError, match="Semantic search"):
        client.search(query="test", mode="semantic")


def test_search_with_fuzzy_mode_raises_not_implemented(
    client: SiphonClient,
) -> None:
    """search with mode='fuzzy' should raise NotImplementedError."""
    with pytest.raises(NotImplementedError, match="Fuzzy search"):
        client.search(query="test", mode="fuzzy")


def test_list_all_calls_repository_list_all(
    client: SiphonClient,
    mock_repository: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """list_all should call repository.list_all with correct parameters."""
    mock_repository.list_all.return_value = [sample_content]

    result = client.list_all(
        source_type=SourceType.ARTICLE,
        limit=10,
    )

    mock_repository.list_all.assert_called_once_with(
        source_type=SourceType.ARTICLE,
        date_filter=None,
        limit=10,
    )
    assert isinstance(result, Collection)
    assert result.count() == 1


def test_get_latest_calls_repository_get_last_processed_content(
    client: SiphonClient,
    mock_repository: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """get_latest should call repository.get_last_processed_content."""
    mock_repository.get_last_processed_content.return_value = sample_content

    result = client.get_latest()

    mock_repository.get_last_processed_content.assert_called_once()
    assert result == sample_content


def test_get_latest_returns_none_when_no_content(
    client: SiphonClient,
    mock_repository: MagicMock,
) -> None:
    """get_latest should return None when repository returns None."""
    mock_repository.get_last_processed_content.return_value = None

    result = client.get_latest()

    assert result is None


def test_find_related_raises_not_implemented(
    client: SiphonClient,
) -> None:
    """find_related should raise NotImplementedError (requires semantic search)."""
    with pytest.raises(NotImplementedError, match="Semantic search"):
        client.find_related(["uri1", "uri2"], "related query")

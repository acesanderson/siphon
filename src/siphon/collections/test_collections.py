# test_siphon_query_progression.py
import pytest
from siphon.collections.corpus.siphon_corpus import CorpusFactory
from siphon.data.type_definitions.source_type import SourceType
from dbclients import get_postgres_client

# =============================================================================
# LEVEL 1: Basic Infrastructure (from previous tests)
# =============================================================================


def test_library_snapshot():
    """Basic snapshot from entire library"""
    corpus = CorpusFactory.from_library()
    snapshot = corpus.snapshot()


def test_corpus_len():
    """Count items in corpus"""
    corpus = CorpusFactory.from_library()
    count = len(corpus)

    assert isinstance(count, int)
    assert count >= 0


def test_query_creation():
    """Create query from corpus"""
    corpus = CorpusFactory.from_library()
    query = corpus.query()

    assert query is not None
    assert hasattr(query, "corpus")


def test_query_to_list():
    """Convert query to list"""
    corpus = CorpusFactory.from_library()
    items = corpus.query().to_list()

    assert isinstance(items, list)
    assert len(items) == len(corpus)


# =============================================================================
# LEVEL 2: Basic Filtering Infrastructure
# =============================================================================


def test_filter_by_source_type_single():
    """Filter corpus to specific source type"""
    corpus = CorpusFactory.from_library()
    youtube_corpus = corpus.filter_by_source_type(SourceType.YOUTUBE)

    assert len(youtube_corpus) <= len(corpus)
    # All items should be YouTube
    for item in youtube_corpus:
        assert item.uri.sourcetype == SourceType.YOUTUBE


def test_filter_by_source_type_maintains_interface():
    """Filtered corpus should still be a siphonCorpus"""
    corpus = CorpusFactory.from_library()
    filtered = corpus.filter_by_source_type(SourceType.DOC)

    # Should still be queryable
    query = filtered.query()
    assert query is not None
    assert len(filtered) <= len(corpus)


def test_filter_returns_new_corpus():
    """Filtering should return a new corpus instance"""
    corpus = CorpusFactory.from_library()
    filtered = corpus.filter_by_source_type(SourceType.ARTICLE)

    assert filtered is not corpus
    assert type(filtered).__name__ in ["DatabaseCorpus", "InMemoryCorpus"]


def test_source_type_counts_basic():
    """Get breakdown by source type"""
    corpus = CorpusFactory.from_library()
    counts = corpus.get_source_type_counts()

    assert isinstance(counts, dict)
    assert all(isinstance(k, SourceType) for k in counts.keys())
    assert all(isinstance(v, int) for v in counts.values())


# =============================================================================
# LEVEL 3: Query Interface Foundation
# =============================================================================


def test_query_filter_delegation():
    """Query should delegate filtering to corpus"""
    corpus = CorpusFactory.from_library()
    query = corpus.query()

    # This should work and return a new query
    filtered_query = query.filter_by_source_type(SourceType.YOUTUBE)
    assert filtered_query is not query
    assert type(filtered_query).__name__ == "siphonQuery"


def test_query_terminal_operations():
    """Terminal operations should return results, not queries"""
    corpus = CorpusFactory.from_library()
    query = corpus.query()

    # These should NOT return siphonQuery objects
    results = query.to_list()
    assert isinstance(results, list)

    count = query.count()
    assert isinstance(count, int)

    exists = query.exists()
    assert isinstance(exists, bool)


def test_query_first_and_last():
    """First and last operations"""
    corpus = CorpusFactory.from_library()
    query = corpus.query()

    first_item = query.first()
    last_item = query.last()

    if len(corpus) > 0:
        assert first_item is not None
        assert last_item is not None
        # They might be the same if corpus has only one item
        assert hasattr(first_item, "uri")
        assert hasattr(last_item, "uri")
    else:
        assert first_item is None
        assert last_item is None


def test_empty_corpus_query_handling():
    """Handle empty corpus gracefully"""
    empty_corpus = CorpusFactory.from_processed_content_list([])
    query = empty_corpus.query()

    assert query.count() == 0
    assert query.first() is None
    assert query.last() is None
    assert query.exists() is False
    assert query.to_list() == []


# =============================================================================
# LEVEL 4: Basic Monadic Conduiting
# =============================================================================


def test_simple_filter_conduit():
    """Conduit one filter operation"""
    corpus = CorpusFactory.from_library()

    results = corpus.query().filter_by_source_type(SourceType.ARTICLE).to_list()

    for item in results:
        assert item.uri.sourcetype == SourceType.ARTICLE


def test_filter_plus_limit():
    """Conduit filter and limit operations"""
    corpus = CorpusFactory.from_library()

    results = corpus.query().filter_by_source_type(SourceType.DOC).limit(3).to_list()

    assert len(results) <= 3
    for item in results:
        assert item.uri.sourcetype == SourceType.DOC


def test_monadic_returns_new_instances():
    """Each monadic operation should return a new siphonQuery"""
    corpus = CorpusFactory.from_library()
    original_query = corpus.query()

    filtered_query = original_query.filter_by_source_type(SourceType.YOUTUBE)
    limited_query = filtered_query.limit(5)

    # Each should be a different query object
    assert original_query is not filtered_query
    assert filtered_query is not limited_query

    # But they should all be siphonQuery instances
    assert type(original_query).__name__ == "siphonQuery"
    assert type(filtered_query).__name__ == "siphonQuery"
    assert type(limited_query).__name__ == "siphonQuery"


def test_conduiting_preserves_state():
    """Conduited operations should accumulate correctly"""
    corpus = CorpusFactory.from_library()

    # This conduit should apply both filter and limit
    results = (
        corpus.query().filter_by_source_type(SourceType.ARTICLE).limit(2).to_list()
    )

    assert len(results) <= 2
    for item in results:
        assert item.uri.sourcetype == SourceType.ARTICLE


# =============================================================================
# LEVEL 5: Content-Based Operations
# =============================================================================


def test_filter_by_content_basic():
    """Basic content text search"""
    corpus = CorpusFactory.from_library()

    ai_content = corpus.query().filter_by_content("AI").to_list()

    # Should find content mentioning AI
    for item in ai_content:
        content_text = item.context.lower()
        assert "ai" in content_text or "artificial intelligence" in content_text


def test_content_search_case_insensitive():
    """Content search should be case insensitive"""
    corpus = CorpusFactory.from_library()

    results_lower = corpus.query().filter_by_content("strategy").count()
    results_upper = corpus.query().filter_by_content("STRATEGY").count()
    results_mixed = corpus.query().filter_by_content("Strategy").count()

    # Should return same count regardless of case
    assert results_lower == results_upper == results_mixed


def test_content_search_with_source_filter():
    """Combine content search with source type filtering"""
    corpus = CorpusFactory.from_library()

    strategy_docs = (
        corpus.query()
        .filter_by_source_type(SourceType.DOC)
        .filter_by_content("strategy")
        .to_list()
    )

    for item in strategy_docs:
        assert item.uri.sourcetype == SourceType.DOC
        assert "strategy" in item.context.lower()


def test_content_search_empty_results():
    """Content search with no matches should return empty"""
    corpus = CorpusFactory.from_library()

    # Search for something very unlikely to exist
    results = corpus.query().filter_by_content("xyzabc123nonexistent").to_list()

    assert len(results) == 0


# =============================================================================
# LEVEL 6: Ordering and Pagination
# =============================================================================


def test_order_by_date_basic():
    """Basic date ordering"""
    corpus = CorpusFactory.from_library()

    results = corpus.query().order_by_date(ascending=False).limit(5).to_list()

    assert len(results) <= 5
    # Should be ordered by date (newest first)
    if len(results) > 1:
        for i in range(len(results) - 1):
            # Note: This assumes your ProcessedContent has a created_at or similar field
            # You might need to adjust based on your actual date field
            assert hasattr(results[i], "uri")  # Basic check for now


def test_limit_and_offset():
    """Test pagination with limit and offset"""
    corpus = CorpusFactory.from_library()

    first_page = corpus.query().limit(3).to_list()

    second_page = corpus.query().offset(3).limit(3).to_list()

    assert len(first_page) <= 3
    assert len(second_page) <= 3

    # Pages should be different (assuming corpus has >3 items)
    if len(corpus) > 3:
        first_uris = {item.uri.uri for item in first_page}
        second_uris = {item.uri.uri for item in second_page}
        assert first_uris != second_uris


def test_order_with_content_filter():
    """Combine ordering with content filtering"""
    corpus = CorpusFactory.from_library()

    results = (
        corpus.query()
        .filter_by_content("AI")
        .order_by_date(ascending=False)
        .limit(3)
        .to_list()
    )

    assert len(results) <= 3
    for item in results:
        assert (
            "ai" in item.context.lower()
            or "artificial intelligence" in item.context.lower()
        )


def test_paginate_helper():
    """Test pagination helper method"""
    corpus = CorpusFactory.from_library()

    page_1 = corpus.query().paginate(page_size=2, page_number=1).to_list()

    page_2 = corpus.query().paginate(page_size=2, page_number=2).to_list()

    assert len(page_1) <= 2
    assert len(page_2) <= 2

    if len(corpus) > 2:
        page_1_uris = {item.uri.uri for item in page_1}
        page_2_uris = {item.uri.uri for item in page_2}
        assert page_1_uris != page_2_uris


# =============================================================================
# LEVEL 7: Advanced Content Operations
# =============================================================================


def test_filter_by_title():
    """Filter by title field from synthetic data"""
    corpus = CorpusFactory.from_library()

    results = corpus.query().filter_by_title("LinkedIn").to_list()

    for item in results:
        if item.title:  # Some items might not have titles
            assert "linkedin" in item.title.lower()


def test_multiple_content_filters():
    """Apply multiple content filters"""
    corpus = CorpusFactory.from_library()

    results = (
        corpus.query().filter_by_content("AI").filter_by_content("strategy").to_list()
    )

    for item in results:
        content_lower = item.context.lower()
        assert "ai" in content_lower and "strategy" in content_lower


def test_source_type_multiple():
    """Filter by multiple source types"""
    corpus = CorpusFactory.from_library()

    results = (
        corpus.query()
        .filter_by_source_type([SourceType.DOC, SourceType.YOUTUBE])
        .to_list()
    )

    allowed_types = {SourceType.DOC, SourceType.YOUTUBE}
    for item in results:
        assert item.uri.sourcetype in allowed_types


def test_filter_by_tags():
    """Filter by tags (if any content has tags)"""
    corpus = CorpusFactory.from_library()

    # This might return empty if no content has tags yet
    results = corpus.query().filter_by_tags(["strategy"]).to_list()

    # Just verify it doesn't crash
    assert isinstance(results, list)


# =============================================================================
# LEVEL 8: Semantic Search Foundation
# =============================================================================


def test_semantic_search_basic():
    """Basic semantic search functionality"""
    corpus = CorpusFactory.from_library()

    results = corpus.query().semantic_search("artificial intelligence", k=3).to_list()

    assert len(results) <= 3
    # Results should be relevant to AI (basic check)
    assert all(hasattr(item, "context") for item in results)


def test_semantic_search_with_filters():
    """Combine semantic search with filtering"""
    corpus = CorpusFactory.from_library()

    results = (
        corpus.query()
        .filter_by_source_type(SourceType.YOUTUBE)
        .semantic_search("machine learning", k=5)
        .to_list()
    )

    assert len(results) <= 5
    for item in results:
        assert item.uri.sourcetype == SourceType.YOUTUBE


def test_similar_to_content():
    """Find content similar to a specific item"""
    corpus = CorpusFactory.from_library()
    all_items = corpus.query().to_list()

    if len(all_items) > 0:
        reference_item = all_items[0]
        similar_items = corpus.query().similar_to(reference_item, k=3).to_list()

        assert len(similar_items) <= 3
        # Reference item might be in results
        assert all(hasattr(item, "uri") for item in similar_items)


def test_semantic_search_empty_query():
    """Semantic search with empty query should handle gracefully"""
    corpus = CorpusFactory.from_library()

    results = corpus.query().semantic_search("", k=5).to_list()

    # Should either return empty or handle gracefully
    assert isinstance(results, list)


# =============================================================================
# LEVEL 9: Cross-Source Intelligence
# =============================================================================


def test_cross_source_content_analysis():
    """Find related content across different source types"""
    corpus = CorpusFactory.from_library()

    # Get strategy content from different sources
    doc_strategy = (
        corpus.query()
        .filter_by_source_type(SourceType.DOC)
        .filter_by_content("strategy")
        .to_list()
    )

    youtube_strategy = (
        corpus.query()
        .filter_by_source_type(SourceType.YOUTUBE)
        .filter_by_content("strategy")
        .to_list()
    )

    # Both should exist in a realistic corpus
    # This tests that the same concepts appear across sources
    assert isinstance(doc_strategy, list)
    assert isinstance(youtube_strategy, list)


def test_competitive_intelligence_pattern():
    """Test pattern for competitive analysis"""
    corpus = CorpusFactory.from_library()

    competitive_content = (
        corpus.query()
        .filter_by_content("competitive")
        .semantic_search("market analysis positioning", k=5)
        .to_list()
    )

    assert len(competitive_content) <= 5
    for item in competitive_content:
        content_lower = item.context.lower()
        assert "competitive" in content_lower or "market" in content_lower


def test_ai_trend_analysis():
    """Pattern for analyzing AI trends across sources"""
    corpus = CorpusFactory.from_library()

    ai_trends = (
        corpus.query()
        .filter_by_content("AI")
        .order_by_date(ascending=False)
        .limit(10)
        .to_list()
    )

    assert len(ai_trends) <= 10
    for item in ai_trends:
        content_lower = item.context.lower()
        assert "ai" in content_lower or "artificial intelligence" in content_lower


def test_source_type_distribution_analysis():
    """Analyze content distribution across source types"""
    corpus = CorpusFactory.from_library()

    # Get AI content from each major source type
    source_types = [SourceType.DOC, SourceType.YOUTUBE, SourceType.ARTICLE]
    distribution = {}

    for source_type in source_types:
        count = (
            corpus.query()
            .filter_by_source_type(source_type)
            .filter_by_content("AI")
            .count()
        )
        distribution[source_type] = count

    # Verify we got some distribution data
    assert isinstance(distribution, dict)
    assert len(distribution) == 3


# =============================================================================
# LEVEL 10: Collection Transformations
# =============================================================================


def test_query_to_corpus_conversion():
    """Convert query results to new corpus"""
    corpus = CorpusFactory.from_library()

    new_corpus = corpus.query().filter_by_content("strategy").to_corpus()

    # Should be a new corpus with filtered content
    assert new_corpus is not corpus
    assert hasattr(new_corpus, "query")
    assert len(new_corpus) <= len(corpus)


def test_corpus_to_sourdough_basic():
    """Convert filtered corpus to Sourdough collection"""
    corpus = CorpusFactory.from_library()

    strategy_corpus = (
        corpus.query()
        .filter_by_content("strategy")
        .filter_by_source_type(SourceType.DOC)
        .to_corpus()
    )

    sourdough = strategy_corpus.query().to_sourdough(
        max_tokens=1000, focus_areas=["strategy"]
    )

    assert hasattr(sourdough, "get_current_snapshot")
    assert len(sourdough) >= 0  # Might be empty if no strategy docs


def test_sourdough_snapshot_generation():
    """Test Sourdough snapshot generation"""
    corpus = CorpusFactory.from_library()

    # Create sourdough with any available content
    limited_corpus = corpus.query().limit(5).to_corpus()
    sourdough = limited_corpus.query().to_sourdough(max_tokens=500)

    snapshot = sourdough.get_current_snapshot()

    assert isinstance(snapshot, str)
    if len(sourdough) > 0:
        assert "Strategic Snapshot" in snapshot


def test_database_to_memory_conversion():
    """Convert database corpus to in-memory corpus"""
    db_corpus = CorpusFactory.from_library()

    memory_corpus = (
        db_corpus.query()
        .filter_by_source_type(SourceType.ARTICLE)
        .limit(10)
        .to_corpus()
    )

    # Should be convertible and queryable
    assert hasattr(memory_corpus, "query")
    query_from_memory = memory_corpus.query()
    assert query_from_memory is not None

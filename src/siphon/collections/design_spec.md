### The Flow
- You start with a corpus: Either from your database (DatabaseCorpus) or from some files you loaded (InMemoryCorpus)
- You create a query: Call corpus.query() to get a SiphonQuery object that wraps your corpus
- You conduit operations: query.filter_by_source_type(YouTube).filter_by_content("AI").limit(10)

### EVENTUAL IMPLEMENTATIONS --
- databasecorpus to have more methods implemented; for now we go to InMemory immediately after querying
- lazy evaluation of queries -- like in pandas, build up a query object and only execute when needed; for now we just do greedy evaluation


"""
# example 1: database → query → in-memory
all_content = corpusfactory.from_library()
research_query = all_content.query()\
   .filter_by_source_type(sourcetype.youtube)\
   .filter_by_tags(["ai", "research"])\
   .limit(50)
research_corpus = research_query.to_corpus()

# example 2: direct corpus operations
youtube_corpus = corpusfactory.from_library()\
   .filter_by_source_type(sourcetype.youtube)

# example 3: complex query conduit
strategic_content = siphonquery(corpusfactory.from_library())\
   .filter_by_date_range(last_30_days)\
   .semantic_search("strategic planning")\
   .order_by_date(ascending=false)\
   .limit(20)\
   .to_sourdough(focus_areas=["strategy", "planning"])

# example 4: in-memory corpus from files
local_corpus = corpusfactory.from_directory("./docs")\
   .query()\
   .filter_by_content("important")\
   .to_corpus()
"""






# collections module design specification

## overview

the `collections/` module provides comprehensive interfaces for managing, querying, and analyzing collections of `processedcontent` objects. this module bridges the gap between individual content processing (handled by core siphon) and advanced content analysis workflows.

## directory structure

```
collections/
├── __init__.py           # main exports and convenience imports
├── readme.md            # this specification
├── corpus/              # collection management and construction
│   ├── processed_corpus.py      # in-memory collections with rich operations
│   ├── processed_library.py     # database-backed collection interface
│   ├── sourdough.py             # auto-curating strategic knowledge base
│   └── specialized/             # domain-specific corpus types
│       ├── research_corpus.py   # multi-document synthesis collections
│       ├── temporal_corpus.py   # time-aware collections
│       └── domain_corpus.py     # subject-matter specialized collections
├── query/               # query interfaces and search implementations
│   ├── siphon_query.py          # main query interface (corpus-agnostic)
│   ├── builders/                # query construction utilities
│   │   ├── query_builder.py     # fluent query construction
│   │   ├── filter_builder.py    # complex filtering logic
│   │   └── aggregation_builder.py # analytics and grouping
│   ├── engines/                 # different search implementations
│   │   ├── fulltext_search.py   # postgresql full-text search
│   │   ├── semantic_search.py   # chromadb vector similarity
│   │   ├── graph_search.py      # neo4j relationship queries
│   │   └── hybrid_search.py     # combined search strategies
│   ├── filters/                 # reusable filtering components
│   │   ├── metadata_filters.py  # source type, date, size filters
│   │   ├── content_filters.py   # text-based filtering
│   │   └── semantic_filters.py  # ai-powered content classification
│   └── snapshot.py              # library overview and statistics
└── analytics/           # Advanced analysis and insights
    ├── content_analytics.py     # Content analysis and metrics
    ├── relationship_discovery.py # Find connections between content
    ├── trend_analysis.py        # Temporal pattern detection
    └── export/                  # Export formats for external tools
        ├── markdown_export.py
        ├── json_export.py
        └── research_export.py
```

## Core Design Principles

### 1. **Corpus-Agnostic Querying**
All query operations work on any `ProcessedCorpus`, whether it's:
- In-memory collections (`ProcessedCorpus.from_directory()`)
- Database-backed collections (`ProcessedCorpus.from_library()`)
- Specialized collections (`Sourdough`, `ResearchCorpus`)

### 2. **Composable Query Building**
```python
# Fluent interface for complex queries
results = (SiphonQuery(corpus)
    .filter_by_source_type(SourceType.YOUTUBE)
    .filter_by_date_range(last_month, today)
    .search("machine learning")
    .semantic_search("AI strategy", k=10)
    .limit(20)
    .execute())
```

### 3. **Pluggable Search Engines**
Different search strategies can be combined:
- **Full-text**: PostgreSQL native search
- **Semantic**: ChromaDB vector similarity
- **Graph**: Neo4j relationship traversal
- **Hybrid**: Combine multiple approaches with ranking

### 4. **Lazy Evaluation**
Queries are constructed as query objects and executed only when needed, allowing for:
- Query optimization
- Caching strategies
- Progress tracking for long operations

## Implementation Strategy

### Query Interface Evolution
```python
class SiphonQuery:
    """Main query interface - starts simple, grows sophisticated."""
    
    # Phase 1: Basic functionality
    def last(self, n: int = 1) -> ProcessedCorpus
    def search(self, query: str) -> ProcessedCorpus
    def filter_by_source_type(self, source_type: SourceType) -> ProcessedCorpus
    
    # Phase 2: Advanced filtering
    def filter_by_date_range(self, start: datetime, end: datetime) -> ProcessedCorpus
    def filter_by_size(self, min_chars: int, max_chars: int) -> ProcessedCorpus
    def filter_by_metadata(self, **criteria) -> ProcessedCorpus
    
    # Phase 3: Semantic capabilities
    def semantic_search(self, query: str, k: int = 10) -> ProcessedCorpus
    def find_similar(self, content: ProcessedContent, k: int = 10) -> ProcessedCorpus
    def cluster_by_topic(self, n_clusters: int = 5) -> dict[str, ProcessedCorpus]
    
    # Phase 4: Advanced analytics
    def trend_analysis(self, time_window: timedelta) -> TrendReport
    def relationship_discovery(self) -> RelationshipGraph
    def content_analytics(self) -> AnalyticsReport
```

### Search Engine Architecture
```python
class SearchEngine(ABC):
    """Base class for different search implementations."""
    
    @abstractmethod
    def search(self, corpus: ProcessedCorpus, query: SearchQuery) -> SearchResults
    
    @abstractmethod
    def supports_query_type(self, query_type: QueryType) -> bool

# Implementations handle specific search types
class FullTextSearchEngine(SearchEngine): ...
class SemanticSearchEngine(SearchEngine): ...
class GraphSearchEngine(SearchEngine): ...

# Hybrid engine routes queries to appropriate engines
class HybridSearchEngine(SearchEngine):
    def search(self, corpus, query):
        # Route to best engine(s) for query type
        # Combine and rank results
```

### Progressive Enhancement

**Phase 1: Foundation** (Current Priority)
- Migrate existing query functionality
- Implement basic SiphonQuery interface
- Set up directory structure

**Phase 2: Advanced Filtering**
- Complex metadata filtering
- Date range and temporal queries
- Content-based filtering (length, complexity)

**Phase 3: Semantic Search**
- ChromaDB integration for vector similarity
- Semantic clustering and topic discovery
- Content relationship detection

**Phase 4: Graph Analysis**
- Neo4j integration for entity relationships
- Content citation and reference networks
- Knowledge graph construction

**Phase 5: Analytics & Insights**
- Trend analysis and pattern detection
- Content gap analysis
- Strategic intelligence automation

## Integration Points

### With Core Siphon
- Collections consume `ProcessedContent` objects
- Query results return `ProcessedCorpus` for further processing
- Maintains compatibility with existing caching and storage

### With External Systems
- **ChromaDB**: Vector embeddings for semantic search
- **Neo4j**: Graph relationships and entity networks  
- **PostgreSQL**: Full-text search and metadata queries
- **Export Formats**: Markdown, JSON, research reports

### With User Workflows
- **CLI Tools**: Rich terminal interfaces for query exploration
- **Research Scripts**: Multi-document synthesis and analysis
- **Strategic Intelligence**: Auto-updating knowledge bases (Sourdough)
- **API Endpoints**: Programmatic access for external tools

## Success Metrics

1. **Query Performance**: Sub-second response for typical queries
2. **Scalability**: Handle 10K+ ProcessedContent objects efficiently  
3. **Flexibility**: Support 80% of user query needs without custom code
4. **Usability**: Intuitive interfaces that match user mental models
5. **Extensibility**: Easy to add new search engines and corpus types

This architecture supports both simple use cases (finding recent content) and sophisticated workflows (multi-modal semantic analysis) while maintaining the clean abstractions that make Siphon extensible and maintainable.

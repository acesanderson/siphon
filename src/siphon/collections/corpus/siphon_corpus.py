"""
SiphonCorpus - Lightweight wrapper around collections of ProcessedContent objects

Provides convenience functions for managing and constructing ProcessedContent. To query a SiphonCorpus, you should attach it to a SiphonQuery object.

A SiphonCorpus can be constructed from a CorpusFactory, which can take various sources:
- Entire library of ProcessedContent from the database (DatabaseCorpus)
- Files in a directory (e.g., markdown, PDFs)
- List of URLs (e.g., YouTube, GitHub, articles)
- Content tagged with specific tags (not yet implemented)
- User-defined queries (not yet implemented) -- i.e. a SiphonQuery object
- Existing list of ProcessedContent objects
- TBD

A SiphonCorpus, on initialization, will also have access to the following (either pre-existing for persistent, or created on-the-fly for in-memory):
- A lightweight in-memory representation of the corpus
- a vector store for similarity search (TBD)
- a graph representation of the corpus (TBD)
- NER, topic modeling, and other NLP features (TBD)
- Automatic summarization of content (TBD)
- Automatic tagging and categorization (TBD)

## Architecture

We define an abstract base class `SiphonCorpus` that provides a rich interface.

We then implement:
- DatabaseCorpus (which uses pgres for specific queries, and leverages persistent Chroma and Neo4j databases, as well as library-wide AI tagging etc.)
- InMemoryCorpus (which is an in-memory set of ProcessedContent objects, with ephemeral chroma and networkx instead of neo4j)

These would use the same interface, but have different implementations for the underlying storage and retrieval mechanisms.

We then have a `CorpusFactory` that provides methods to create the appropriate corpus type based on the source:
"""

from siphon.data.processed_content import ProcessedContent
from siphon.data.type_definitions.source_type import SourceType
from psycopg2.extras import RealDictCursor
from typing import override
from collections.abc import Iterator
from abc import ABC, abstractmethod
from pathlib import Path


class SiphonCorpus(ABC):
    """
    Abstract interface - all corpus types look the same to SiphonQuery.
    """

    # Collection Management
    @abstractmethod
    def add(self, content: ProcessedContent) -> None: ...

    @abstractmethod
    def remove(self, content: ProcessedContent) -> None: ...

    @abstractmethod
    def remove_by_uri(self, uri: str) -> bool: ...

    # Iteration & Access
    @abstractmethod
    def __iter__(self) -> Iterator[ProcessedContent]: ...

    @abstractmethod
    def __len__(self) -> int: ...

    @abstractmethod
    def __contains__(self, content: ProcessedContent) -> bool: ...

    # Query Interface (returns new corpus for conduiting)
    @abstractmethod
    def filter_by_source_type(self, source_type: SourceType) -> "SiphonCorpus": ...

    @abstractmethod
    def filter_by_date_range(self, start_date, end_date) -> "SiphonCorpus": ...

    @abstractmethod
    def filter_by_tags(self, tags: list[str]) -> "SiphonCorpus": ...

    # Metadata & Views
    @abstractmethod
    def snapshot(self) -> str: ...

    @abstractmethod
    def get_source_type_counts(self) -> dict[SourceType, int]: ...

    @abstractmethod
    def is_empty(self) -> bool: ...

    # Query Entry Point
    @abstractmethod
    def query(self) -> "SiphonQuery": ...


class InMemoryCorpus(SiphonCorpus):
    """
    In-memory corpus for fast operations on materialized data
    """

    def __init__(self, source: str, corpus: list[ProcessedContent] = None):
        self.source = source
        self.corpus = corpus if corpus is not None else []  # Fix: Use list, not dict
        # Vector store stuff
        self.description_collection = None
        self.chunked_context_collection = None
        self.vector_store_created = False

    # Create vectors and graphs on the fly as needed
    def _create_vector_store(self):
        import chromadb
        from chromadb.utils import embedding_functions
        import torch

        # Check GPU availability
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {device}")

        client = chromadb.EphemeralClient()

        # Check if corpus is empty
        if not self.corpus:
            print("Warning: Cannot create vector store - corpus is empty")
            return

        # Create GPU-enabled embedding function
        # Option 1: Use sentence-transformers with GPU support
        try:
            embedding_function = (
                embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2",  # Fast, good quality model
                    device=device,
                )
            )
        except Exception as e:
            embedding_function = embedding_functions.DefaultEmbeddingFunction()

        # Alternative Option 2: Use Hugging Face transformers directly
        # embedding_function = embedding_functions.HuggingFaceEmbeddingFunction(
        #     api_key="your_hf_token",  # Only needed for gated models
        #     model_name="sentence-transformers/all-MiniLM-L6-v2"
        # )

        # We want ephemeral collections for: uri:description, uri:chunked_context
        description_collection = client.create_collection(
            name="siphon_in_memory_descriptions", embedding_function=embedding_function
        )

        # Collect valid descriptions
        valid_descriptions = []
        valid_desc_ids = []
        for content in self.corpus:
            if (
                content.description and content.description.strip()
            ):  # Check for non-empty description
                valid_descriptions.append(content.description)
                valid_desc_ids.append(content.uri.uri)

        # Add descriptions in batches to avoid size limits
        if valid_descriptions:
            batch_size = 500  # Smaller batches for GPU to avoid memory issues
            print(
                f"Adding {len(valid_descriptions)} descriptions in batches of {batch_size}"
            )
            for i in range(0, len(valid_descriptions), batch_size):
                batch_docs = valid_descriptions[i : i + batch_size]
                batch_ids = valid_desc_ids[i : i + batch_size]
                print(
                    f"Adding description batch {i // batch_size + 1}: {len(batch_docs)} items"
                )
                description_collection.add(
                    documents=batch_docs,
                    ids=batch_ids,
                )
        self.description_collection = description_collection

        # Handle chunked context - use same embedding function for consistency
        chunked_context_collection = client.create_collection(
            name="siphon_in_memory_chunked_context",
            embedding_function=embedding_function,
        )

        all_chunks = []
        all_chunk_ids = []

        for content in self.corpus:
            if (
                content.context and content.context.strip()
            ):  # Check for non-empty context
                # Chunk the context into smaller pieces for better search
                chunks = [
                    content.context[i : i + 500]
                    for i in range(0, len(content.context), 500)
                    if content.context[
                        i : i + 500
                    ].strip()  # Only include non-empty chunks
                ]
                chunk_ids = [f"{content.uri.uri}_chunk_{j}" for j in range(len(chunks))]

                all_chunks.extend(chunks)
                all_chunk_ids.extend(chunk_ids)

        # Add chunks in batches to avoid ChromaDB batch size limits
        if all_chunks:
            batch_size = 500  # Smaller batches for GPU processing
            print(
                f"Adding {len(all_chunks)} chunks in batches of {batch_size} using {device}"
            )
            for i in range(0, len(all_chunks), batch_size):
                batch_docs = all_chunks[i : i + batch_size]
                batch_ids = all_chunk_ids[i : i + batch_size]
                print(
                    f"Adding chunk batch {i // batch_size + 1}/{(len(all_chunks) - 1) // batch_size + 1}: {len(batch_docs)} chunks"
                )
                chunked_context_collection.add(documents=batch_docs, ids=batch_ids)

        self.chunked_context_collection = chunked_context_collection
        self.vector_store_created = True
        print("Vector store creation completed!")

    def _query_vector_store(self, vector_collection, query: str, k: int):
        if not self.vector_store_created:
            self._create_vector_store()

        if vector_collection is None:
            return {"documents": [[]], "ids": [[]], "distances": [[]]}

        results = vector_collection.query(query_texts=[query], n_results=k)
        return results

    # Collection Management
    @override
    def add(self, content: ProcessedContent) -> None:
        if content not in self.corpus:
            self.corpus.append(content)
            # Reset vector store so it gets recreated with new content
            self.vector_store_created = False

    @override
    def remove(self, content: ProcessedContent) -> None:
        self.corpus.remove(content)
        # Reset vector store so it gets recreated without removed content
        self.vector_store_created = False

    @override
    def remove_by_uri(self, uri: str) -> bool:
        to_remove = next((c for c in self.corpus if c.uri == uri), None)
        if to_remove:
            self.corpus.remove(to_remove)
            # Reset vector store
            self.vector_store_created = False
            return True
        return False

    # Iteration & Access
    @override
    def __iter__(self) -> Iterator[ProcessedContent]:
        return iter(self.corpus)

    @override
    def __len__(self) -> int:
        return len(self.corpus)

    @override
    def __contains__(self, content: ProcessedContent) -> bool:
        return content in self.corpus

    # Query Interface (returns new InMemoryCorpus with filtered data)
    @override
    def filter_by_source_type(self, source_type: SourceType) -> "InMemoryCorpus":
        filtered = [
            c for c in self.corpus if c.source_type == source_type
        ]  # Fix: Use list comprehension
        return InMemoryCorpus(
            source=f"{self.source}|source_type={source_type}", corpus=filtered
        )

    @override
    def filter_by_date_range(self, start_date, end_date) -> "InMemoryCorpus":
        filtered = [
            c
            for c in self.corpus
            if c.date_added and start_date <= c.date_added <= end_date
        ]  # Fix: Use list comprehension
        return InMemoryCorpus(
            source=f"{self.source}|date_range={start_date}_{end_date}", corpus=filtered
        )

    @override
    def filter_by_tags(self, tags: list[str]) -> "InMemoryCorpus":
        filtered = [
            c for c in self.corpus if any(tag in c.tags for tag in tags)
        ]  # Fix: Use list comprehension
        return InMemoryCorpus(
            source=f"{self.source}|tags={','.join(tags)}", corpus=filtered
        )

    # Rest of your methods remain the same...
    def text(self) -> str: ...

    def to_dataframe(self): ...

    @override
    def snapshot(self):
        from siphon.collections.query.snapshot import generate_snapshot

        generate_snapshot(self.corpus)

    @override
    def get_source_type_counts(self) -> dict[SourceType, int]: ...

    @override
    def is_empty(self) -> bool:
        return len(self.corpus) == 0

    @override
    def query(self) -> "SiphonQuery":
        from siphon.collections.query.siphon_query import SiphonQuery

        return SiphonQuery(self)


class DatabaseCorpus(SiphonCorpus):
    """
    Database-backed corpus with lazy SQL query building.
    Note: This is a read-only corpus for now; adding/removing content should be done via dedicated ingestion/removal functions.

    """

    raise NotImplementedError("DatabaseCorpus is not yet implemented.")

    # def __init__(self, db_connection=get_db_connection):
    #     """
    #     Initialize a database-backed corpus.
    #
    #     Args:
    #         db_connection_func: contextlib.contextmanager to get a database connection
    #     """
    #     self.db_connection = db_connection
    #
    # @override
    # def __len__(self) -> int:
    #     """Return the number of items in the corpus."""
    #     with self.db_connection() as conn, conn.cursor() as cursor:
    #         cursor.execute("SELECT COUNT(*) FROM processed_content")
    #         count = cursor.fetchone()[0]
    #     return count
    #
    # # Collection Management
    # @override
    # def add(self, content: ProcessedContent) -> None:
    #     raise NotImplementedError()
    #
    # @override
    # def remove(self, content: ProcessedContent) -> None:
    #     raise NotImplementedError()
    #
    # @override
    # def remove_by_uri(self, uri: str) -> bool:
    #     raise NotImplementedError()
    #
    # # Iteration & Access
    # @override
    # def __iter__(self):
    #     with (
    #         self.db_connection() as conn,
    #         conn.cursor(cursor_factory=RealDictCursor) as cursor,
    #     ):
    #         cursor.execute("SELECT * FROM processed_content")
    #         while True:
    #             rows = cursor.fetchmany(1000)  # Batch of 1000
    #             if not rows:
    #                 break
    #             for row in rows:
    #                 yield ProcessedContent.model_validate_from_cache(row["data"])
    #
    # @override
    # def __contains__(self, content: ProcessedContent) -> bool:
    #     raise NotImplementedError()
    #
    # # Query Interface (returns new DatabaseCorpus with modified SQL)
    # @override
    # def filter_by_source_type(self, source_type: SourceType) -> "DatabaseCorpus":
    #     raise NotImplementedError()
    #
    # @override
    # def filter_by_date_range(self, start_date, end_date) -> "DatabaseCorpus":
    #     raise NotImplementedError()
    #
    # @override
    # def filter_by_tags(self, tags: list[str]) -> "DatabaseCorpus":
    #     raise NotImplementedError()
    #
    # # Database-specific methods
    # def _get_all_processed_content(self) -> "list[ProcessedContent]":
    #     from siphon.database.postgres.PGRES_processed_content import get_all_siphon
    #
    #     return get_all_siphon()
    #
    # # Metadata & Views
    # @override
    # def snapshot(self):
    #     from siphon.collections.query.snapshot import generate_snapshot
    #
    #     generate_snapshot()
    #
    # @override
    # def get_source_type_counts(self) -> dict[SourceType, int]: ...
    #
    # @override
    # def is_empty(self) -> bool: ...
    #
    # @override
    # def query(self) -> "SiphonQuery":
    #     """
    #     Create a SiphonQuery instance for this corpus.
    #     For now, this immediately goes to InMemoryCorpus.
    #     As database grows and performance degrades, we can implement more queries within DatabaseCorpus and move logic to database layer, at which point this would return self.
    #
    #     """
    #     from siphon.collections.query.siphon_query import SiphonQuery
    #
    #     processed_content_list = self._get_all_processed_content()
    #     corpus = InMemoryCorpus(source="DatabaseCorpus", corpus=processed_content_list)
    #
    #     return SiphonQuery(corpus)
    #


class CorpusFactory:
    """
    Factory for creating appropriate corpus implementations
    """

    # Database-backed creation
    @staticmethod
    def from_library() -> DatabaseCorpus:
        """Create a DatabaseCorpus from the entire library of ProcessedContent."""
        return DatabaseCorpus()

    @staticmethod
    def from_tag(tag: str) -> DatabaseCorpus: ...

    @staticmethod
    def from_date_range(start_date, end_date) -> DatabaseCorpus: ...

    # In-memory creation
    @staticmethod
    def from_directory(
        directory_path: str | Path, pattern: str = "*"
    ) -> InMemoryCorpus: ...

    @staticmethod
    def from_url_list(urls: list[str]) -> InMemoryCorpus: ...

    @staticmethod
    def from_processed_content_list(
        content_list: list[ProcessedContent],
    ) -> InMemoryCorpus: ...

    @staticmethod
    def from_files(file_paths: list[str]) -> InMemoryCorpus: ...


if __name__ == "__main__":
    corpus = CorpusFactory.from_library()
    print(f"Iterated {sum(1 for _ in corpus)} items vs len() = {len(corpus)}")

-- Migration: add pgvector embedding columns to processed_content
-- Run once against the siphon2 database.
-- Requires: PostgreSQL with pgvector extension available.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE processed_content
    ADD COLUMN IF NOT EXISTS embedding vector(384),
    ADD COLUMN IF NOT EXISTS embed_model varchar;

-- HNSW index for cosine-distance nearest-neighbour search.
-- Skips NULL rows automatically. Safe to create on an empty column.
CREATE INDEX IF NOT EXISTS ix_pc_embedding_hnsw
    ON processed_content
    USING hnsw (embedding vector_cosine_ops);

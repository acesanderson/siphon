from __future__ import annotations


def test_engine_pool_size_is_at_least_20():
    """Pool must support at least 20 concurrent connections for batch workloads."""
    from siphon_server.database.postgres.connection import engine
    pool = engine.pool
    assert pool.size() >= 20


def test_engine_pool_overflow_is_at_least_40():
    from siphon_server.database.postgres.connection import engine
    assert engine.pool._max_overflow >= 40


def test_engine_has_pool_pre_ping():
    from siphon_server.database.postgres.connection import engine
    assert engine.pool._pre_ping is True

"""
Verification that PostgreSQL slow-query logging (pg_stat_statements) is
actually enabled. If the extension is not created in the database, every
slow-query read path silently returns empty and the feature is dead.
"""
from sqlalchemy import text

from backend.services.slow_query_service import get_slow_queries, get_summary


def test_pg_stat_statements_available(db_session):
    """The pg_stat_statements extension must exist so slow-query analytics work."""
    summary = get_summary(db_session)
    assert summary.get("available") is True, (
        "pg_stat_statements extension is not installed — slow-query logging "
        "is disabled. Ensure shared_preload_libraries=pg_stat_statements is set "
        "and CREATE EXTENSION pg_stat_statements has run."
    )


def test_slow_query_captured_after_pg_sleep(db_session):
    """A query slower than 500 ms must appear in pg_stat_statements output."""
    db_session.execute(text("SELECT pg_sleep(0.6)"))
    db_session.commit()
    slow = get_slow_queries(db_session, limit=20, min_avg_ms=500.0)
    assert any("pg_sleep" in (q.query_preview or "") for q in slow), (
        "Expected pg_sleep(0.6) to be captured as a slow query."
    )


def test_slow_queries_endpoint_returns_data(client, auth_headers):
    """GET /admin/slow-queries must succeed for an admin and return the list key."""
    response = client.get("/api/v1/admin/slow-queries", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body.get("success") is True
    assert "slow_queries" in body

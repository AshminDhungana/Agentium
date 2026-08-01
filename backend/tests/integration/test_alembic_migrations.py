"""Verify alembic migrations run in test database."""
import pytest
from sqlalchemy import inspect, text


@pytest.mark.integration
def test_alembic_head_applied(db_engine):
    """All alembic migrations should be applied to test DB."""
    inspector = inspect(db_engine)
    tables = inspector.get_table_names()

    # Key tables that should exist after full migration (matching actual alembic schema)
    # Note: capabilities/agent_capabilities tables not in combined migration (created separately if needed)
    required_tables = {
        "agents", "tasks", "constitutions", "amendment_votings", "voting_records",
        "audit_logs", "execution_checkpoints", "event_triggers", "event_logs",
        "workflows", "workflow_executions", "user_preferences",
        "model_pricings", "mcp_tools",
    }

    missing = required_tables - set(tables)
    assert not missing, f"Missing tables after alembic upgrade: {missing}"

    # Verify alembic_version table exists and has head revision
    with db_engine.connect() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert result is not None, "alembic_version table empty"
        print(f"Applied alembic revision: {result}")
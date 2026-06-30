# Agentium Backend

FastAPI application with SQLAlchemy ORM, Alembic migrations, Celery workers, and async PostgreSQL.

## Database Migrations

See [`docs/ALEMBIC_MIGRATIONS.md`](../docs/ALEMBIC_MIGRATIONS.md) for best practices on writing reversible `downgrade()` functions and running the audit/round-trip verification tools.

Quick commands:
```bash
# Run the audit (fast static analysis)
python tests/alembic/audit_migrations.py

# Run the round-trip test (definitive — full upgrade/downgrade cycle)
docker exec -e DATABASE_URL="postgresql://agentium:agentium@host.docker.internal:5432/agentium_test" \
  agentium-backend \
  python /app/tests/alembic/test_downgrade_roundtrip_docker.py
```

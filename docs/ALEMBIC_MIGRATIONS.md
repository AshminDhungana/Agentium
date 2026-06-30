# Alembic Migration Best Practices

Every new database migration must include a complete `downgrade()` function that
reverses every schema change made by `upgrade()`.

## Quick checklist for new migrations

- [ ] `op.create_table()` → `op.drop_table()`
- [ ] `op.add_column()` → `op.drop_column()`
- [ ] `op.create_index()` → `op.drop_index()`
- [ ] `op.create_foreign_key()` → `op.drop_constraint(type_='foreignkey')`
- [ ] `op.create_unique_constraint()` → `op.drop_constraint(type_='unique')`
- [ ] `op.execute("CREATE TYPE ...")` → `op.execute("DROP TYPE IF EXISTS ...")`
- [ ] `op.execute("CREATE FUNCTION ...")` → `op.execute("DROP FUNCTION IF EXISTS ...")`

## Verifying a migration

After writing a new migration, verify it rounds-trip cleanly on a clean database:

```bash
# Run the audit tool to check for missing downgrade functions
python tests/alembic/audit_migrations.py

# Run the Docker-based round-trip test (recommended — full DB lifecycle)
docker compose -f docker-compose.test.yml up -d
docker exec -e DATABASE_URL="postgresql://agentium:agentium@host.docker.internal:5432/agentium_test" \
  agentium-backend \
  python /app/tests/alembic/test_downgrade_roundtrip_docker.py

# Or run the pytest version directly against a running test DB
cd backend
pytest tests/alembic/test_downgrade_coverage.py -v
```

## What to do if the audit flags your migration as PARTIAL

The `audit_migrations.py` script uses static analysis (AST + regex) to count
operations.  It may under-count **batch operations** — loops over tables, batch
drops via `op.execute()`, and `sa.Enum(...).drop()` calls.  If your migration
shows as **PARTIAL** but the round-trip test passes, the migration is fine; the
script simply cannot enumerate all operations in dynamic or raw-SQL blocks.

**Rule of thumb:**  the round-trip test is the definitive truth.  The audit is
a fast smoke test.

## Tips for writing a correct downgrade

1. **Drop in reverse dependency order** — foreign-key child tables before
   parents, indexes before tables, constraints before columns.
2. **Use `IF EXISTS`** when dropping via raw SQL (`DROP TABLE IF EXISTS foo`)
   so the migration stays idempotent and doesn't fail if the object is already
   gone.
3. **Handle circular foreign keys** by dropping the FK constraint first, then
   dropping the table.
4. **Preserve enum types** — if you created an enum with `CREATE TYPE`, drop
   it at the very end of the downgrade.
5. **Clean up indexes explicitly** — even if your database auto-removes indexes
   with the table, dropping them explicitly keeps the SQL clean and avoids
   noise in logs.

## Architecture

All migration files live in `backend/alembic/versions/` and use Alembic's
`autogenerate` or hand-written revision commands.  The canonical entry points
for running migrations are:

| Command | Purpose |
|---------|---------|
| `alembic upgrade head` | Apply all pending migrations |
| `alembic downgrade base` | Roll back everything |
| `alembic downgrade -1` | Roll back the last migration |
| `alembic check` | Verify migration scripts for errors |
| `alembic revision --autogenerate -m "message"` | Generate a new migration |

## CI / Automation

The audit script and round-trip test should be run as part of CI before any
migration is merged:

```bash
#!/bin/sh
cd backend
python tests/alembic/audit_migrations.py
pytest tests/alembic/test_downgrade_coverage.py -v
```

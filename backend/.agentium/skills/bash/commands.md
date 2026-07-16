# Bash Command Cookbook (Agentium)

Run host commands from the repo root; container commands via
`docker compose exec -T backend bash -lc '...'`.

## Tests
- Full backend suite: `docker compose exec -T backend bash -lc "cd /app/backend && pytest"`
- Single file: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/unit/test_x.py -q"`
- Disable coverage gate: append `-o addopts=""`.
- Integration suite: `make test-integration` (uses `docker-compose.test.yml` with the
  env vars from `.github/workflows/integration-tests.yml`).

## Database
- Init: `docker compose exec -T backend python scripts/init_db.py`
- Migrate: `docker compose exec -T backend bash -lc "cd /app/backend && alembic upgrade head"`
- New revision: `... alembic revision -m "message"`
- Inspect: `docker compose exec -T postgres psql -U agentium -d agentium`

## Redis / Chroma
- `docker compose exec redis redis-cli ping`
- Chroma HTTP: `curl -s http://localhost:8001/api/v1/heartbeat`

## Lint / format / type
- `docker compose exec -T backend bash -lc "cd /app/backend && ruff check . && ruff format . && black . && mypy ."`
- `interrogate services/ --fail-under=90`
- `detect-secrets scan`
- `vulture .`

## Logs / health
- `docker compose logs -f <svc>`
- `curl -sf http://localhost:8000/api/health`

## Lifecycle
- `make up|down|restart`; rebuild one service: `docker compose up -d --build <svc>`
- `make audit` (pip-audit + npm audit); `make benchmark`; `make docker-scout`

## Git
- Prefer the `git_tool`; raw `git` is allowed inside the repo mount
  (`/host/<repo>/...` or the bind-mounted `./backend`).

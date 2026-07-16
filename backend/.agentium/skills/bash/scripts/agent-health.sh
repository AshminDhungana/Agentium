#!/usr/bin/env bash
# agent-health.sh — quick Agentium stack health snapshot.
# Safe: read-only; no side effects. Run via:
#   bash -lc '/app/backend/.agentium/skills/bash/scripts/agent-health.sh'
set -euo pipefail
echo "== Agentium service health =="
docker compose ps --format 'table {{.Name}}\t{{.Status}}' || true
echo "== Backend API =="
curl -fsS http://localhost:8000/api/health && echo " OK" || echo " UNREACHABLE"
echo "== Postgres =="
docker compose exec -T postgres pg_isready -U agentium >/dev/null 2>&1 && echo " OK" || echo " DOWN"
echo "== Redis =="
docker compose exec -T redis redis-cli ping 2>/dev/null || echo " DOWN"
echo "== Chroma =="
curl -fsS http://localhost:8001/api/v1/heartbeat >/dev/null 2>&1 && echo " OK" || echo " DOWN"

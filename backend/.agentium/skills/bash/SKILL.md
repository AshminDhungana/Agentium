---
name: bash
description: >-
  Run shell/terminal commands in the Agentium Docker stack safely — pytest,
  alembic, ruff/black/mypy, docker compose, make, and Postgres/Redis/Chroma
  inspection. Covers the ShellTool list-vs-shell rule and safe-bash discipline.
skill_type: automation
domain: devops
complexity: intermediate
tags: [bash, shell, docker, terminal, devops, testing, migrations]
creator_tier: head
---

# Bash for Agentium Agents

Agentium runs entirely in Docker. You execute shell through `ShellTool.execute(command: List[str])`,
which calls `subprocess.run` **without a shell**.

## The ShellTool rule (critical)
Pipes, redirects, `&&`, `||`, `$()`, and globs do NOT work unless you wrap the whole
command in `bash -lc "..."` and quote the inner string:
`bash -lc "docker compose exec -T backend pytest tests/foo.py -q 2>&1 | tail -40"`.

## Two shells
- Host shell: lifecycle via `make` + `docker compose` (`make up`, `make down`,
  `make restart`, `make test-integration`, `make audit`, `make benchmark`,
  `make docker-scout`).
- Container shell (Python 3.11 toolchain: pytest 8.4, alembic 1.14, ruff/black/
  mypy/interrogate/detect-secrets/vulture): reach via
  `docker compose exec -T backend bash -lc '...'`.

## Host path discipline
Follow `tools/host_path.py`: `~` → `/host_home`, other absolute paths → `/host`,
`/tmp` and relative → container-local. Never write Sovereign/user files into the
container filesystem.

## Safe-bash discipline (summary)
See `safety.md`. One-liner: `set -euo pipefail`, quote `"${var}"`, `[[ ]]` not
`[ ]`, no `eval`, check return codes, idempotent, explicit `./` for globs, preview
destructive ops. `ShellTool` already blocks `rm -rf /`, `mkfs`, `dd if=/dev/zero`,
`shutdown`, `reboot`.

## Command cookbook
See `commands.md` for copy-paste recipes (tests, DB/alembic, Redis/Chroma, lint/
format/type, logs/health, lifecycle, git).

## Bundled helpers (scripts & datasets)
This skill ships runnable helpers. The `__SKILL_DIR__` token resolves to this
skill's absolute path inside the container
(`/app/backend/.agentium/skills/bash`). Invoke a helper through `bash -lc`:
`bash -lc '__SKILL_DIR__/scripts/agent-health.sh'`
Datasets (if any) live at `__SKILL_DIR__/datasets/`.

## Error handling & red flags
Unhealthy services, migration conflicts, port clashes, offline model downloads,
secret-scan failures. Agent foot-guns: guessing commands, unquoted vars, ignoring
non-zero exits, unvetted `rm -rf`.

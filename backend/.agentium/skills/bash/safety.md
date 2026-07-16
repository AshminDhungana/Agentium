# Safe Bash Discipline

Grounded in the Google Shell Style Guide and the "unofficial bash strict mode".

## Always
- Start scripts with `#!/usr/bin/env bash` and `set -euo pipefail`.
- Quote every expansion: `"${var}"`, `"$(cmd)"`.
- Prefer `[[ ]]` over `[ ]`; `(( ))` for arithmetic; `==` for string equality.
- Use arrays for argument lists: `flags=(--foo --bar); cmd "${flags[@]}"`. Never
  build command strings.
- Check return values: `if ! cmd; then ...; fi` or inspect `$?` / `PIPESTATUS`.
- Idempotent commands (e.g. `CREATE DATABASE IF NOT EXISTS`, `mkdir -p`).

## Never
- `eval`. No SUID/SGID scripts. Prefer builtins over external commands.
- `rm -rf` with an unguarded variable. Use `./` prefix for globs: `rm -f ./*`
  not `rm -f *` (a file named `-r` would otherwise be interpreted as a flag).
- Write to configs under `/host` or `/host_home` without reading them first.

## Destructive operations
- Preview with `ls`/`echo` before deleting.
- Prefer moving to a temp trash dir over hard deletion during investigation.

## In the Agentium container
- The backend container already runs `set -e` in its entrypoint; your ad-hoc
  `bash -lc` blocks should add `set -euo pipefail` themselves.
- `ShellTool` blocks `rm -rf /`, `mkfs`, `dd if=/dev/zero`, `shutdown`, `reboot`
  — but partial wipes (e.g. `rm -rf /app/*` or `rm -rf ~/*`) are NOT blocked. Stay careful.

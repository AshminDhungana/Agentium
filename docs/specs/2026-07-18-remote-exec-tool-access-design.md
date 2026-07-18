# Design: Isolated Task-Agent Tool Access to the Remote Executor Sandbox

- **Date:** 2026-07-18
- **Spec source:** Core Architecture §3.1 — Isolated Task Agent tool access
- **Status:** approved

## 1. Problem

Agentium's "Brains vs Hands" separation is built: `services/remote_executor/`
runs agent code in an isolated Docker sandbox and returns only structured
summaries (schema, stats, small samples), so raw data / PII never leaves the
container.

However, the sandbox is **unreachable by Task Agents**. A Task Agent's reasoning
loop (`agent_orchestrator._execute_task_inner` → `llm_client.generate_with_tools`)
invokes tools **in-process on the backend / Celery host** via
`tool_registry.execute_tool_async`. The Remote Executor is only exposed through
the REST route `/api/v1/remote-executor/execute`, which hardcodes
`agent_id="00001"` and has **no agent-callable tool** bridging to it. The only
code-execution a Task Agent can currently do is `execute_command`
(`shell_tool`) directly on the host — the opposite of the intended isolation.

**Goal (§3.1 acceptance criteria):** a documented, tested path for a Task Agent
to call at least one file-system tool and one network tool from inside the
sandbox, with PII / raw-data isolation intact.

## 2. Approach

Register a dedicated `remote_exec` tool in the `ToolRegistry` that delegates to
the existing `RemoteExecutorService`, passing the *real* calling agent's
`agentium_id` (not the hardcoded `"00001"`), and returning only the structured
summary. This makes the already-built sandbox actually reachable by Task Agents.

Alternatives considered and rejected:
- **Reuse `execute_command`** — muddies host-vs-sandbox boundaries and tool
  semantics; keeps code execution on the host.
- **Agent-driven persistent-sandbox lifecycle tools** — heavier, currently
  admin-gated, overkill for this scope.

## 3. Spawn-to-Execution Path (documented)

```
Task Agent (3xxxx) reasoning loop
  agent_orchestrator._execute_task_inner
    → llm_client.generate_with_tools (provider tool-calling loop)
      → LLM emits tool_call: remote_exec { code, input_data, network_access, ... }
      → tool_registry.execute_tool_async("remote_exec", ...)        [backend / Celery process]
          → RemoteExecutorService.execute(agent_id=<real agent id>, ...)   [services/remote_executor/service.py]
              → execution_guard.validate_code(code, tier)           [blocks dangerous / restricted imports]
              → SandboxManager.create_sandbox (warm pool or cold start)
              → docker cp code.py + input.json + executor.py
              → docker exec python /tmp/executor.py                 [default network_mode="none"]
              → executor.py: analyze result → schema / stats / sample(≤3 rows)
              → SandboxManager.destroy_sandbox (always, in finally)
          → returns ExecutionSummarySchema (NEVER raw data) back to agent
```

### What the sandbox CAN do
- Run Python 3.11; use pandas / numpy / polars / pyarrow + stdlib.
- Read/write its own scoped tmpfs working dir (`/tmp`).
- Install `dependencies` via pip (with opt-in network).
- Opt-in network egress (bridge mode) for legitimate network tools.

### What the sandbox CANNOT do
- Reach the host filesystem (read-only rootfs + scoped tmpfs; no host mounts).
- See PII / raw data — only shape/schema/stats return across the boundary.
- Use dangerous patterns (`rm -rf /`, `exec`, `eval`, `os.system`,
  `subprocess.run`, `__import__`, etc.) — blocked by `execution_guard`.
- Reach private/IMDS networks when network is opt-in (egress allowlist blocks
  RFC1918, loopback, `169.254.169.254`).

## 4. Sandbox Capability Posture (hardened, defense-in-depth)

Grounded in 2026 agent-sandboxing best practice (Northflank, LangChain,
Docker, Augment Code, IBM):

- **Default-deny network**: `network_mode="none"` unless `network_access=True`.
  When opt-in, use a bridge with an **egress allowlist** — block RFC1918 /
  private ranges, loopback, and cloud IMDS (`169.254.169.254`) to prevent
  credential theft. Allowlist is configurable (default: pip `pypi.org` + any
  hosts the agent explicitly names).
- **Read-only rootfs + scoped tmpfs**: run container `--read-only` with a
  size-capped `tmpfs` `/tmp` mount (`noexec,nosuid,nodev`) for code/input/
  output. Prevents backdoor persistence.
- **Non-root + resource caps**: already non-root (`executor` user), CPU/mem
  capped — retained.
- **Ephemeral**: created per call, destroyed in `finally` — retained.
- **No secrets in sandbox**: backend never mounts `.env` / credentials into the
  sandbox. If network opt-in needs auth, an egress proxy injects it (future;
  out of scope now).

## 5. The `remote_exec` Tool

- New module `backend/tools/remote_exec_tool.py` with
  `async def execute(agent_id, code, input_data=None, dependencies=None,
  network_access=False, timeout_seconds=300, memory_limit_mb=512,
  cpu_limit=1.0) -> dict`.
- Registered in `backend/core/tool_registry.py`:
  - `authorized_tiers = ["3xxxx","4xxxx","5xxxx","6xxxx","7xxxx","8xxxx","9xxxx"]`
    (withheld from `0xxxx`/`1xxxx`/`2xxxx` governance tiers, which already have
    host-level tools; not in `RESTRICTED_FOR_TASK`).
  - Parameters mirror `CodeExecutionRequest` schema (bounded limits).
- Implementation calls `RemoteExecutorService(db=None).execute(...)` with the
  **real calling agent id** and returns the `summary` dict only.
- **Fix:** the REST route's hardcoded `agent_id="00001"` is retained for
  user-initiated calls; the tool path uses the real agent id so audit logs and
  tier-based guard checks are correct.
- **Audit trail:** each `remote_exec` call emits a structured audit log entry
  (agent_id, sandbox_id, status, duration_ms, network flag).

## 6. PII-Isolation Contract (explicit)

Per IBM's "Mask & Rehydrate" pattern (2026): the LLM is a reasoning engine, not
a data store. The executor returns **only**:
- `output_schema` (column → type)
- `row_count`
- `sample` — **max 3 rows, each field truncated to 500 chars**
- `stats` (describe-style aggregates)
- truncated `stdout` / `stderr` (≤1000 chars)

The full raw DataFrame / raw rows **never serialize out of the container**.
This is the hard boundary. The tool's docstring states the contract so agents
and critics know raw data stays in the sandbox.

## 7. Error Handling

- `execution_guard` blocks → tool returns
  `{"status":"blocked","violations":[...]}` so the agent can self-correct.
- Sandbox failure / timeout → `failed` summary with `error_message`; sandbox
  always destroyed in `finally`.
- Network opt-in but blocked by allowlist → connection refused inside sandbox;
  surfaced via `stderr` / `error_message`.

## 8. Testing (Docker-gated integration test)

`backend/tests/integration/test_remote_exec_tool.py`, skipped when Docker is
unavailable (mirrors `test_execution_wait.py`):

1. **FS case** — code writes a file in the sandbox and builds a synthetic
   (non-PII) DataFrame; assert the summary returns schema / row_count and the
   file write succeeded inside the sandbox.
2. **Network case** — `network_access=True` fetches a public URL → success;
   `network_access=False` → unreachable.
3. **PII-isolation case** — code builds a 1000-row DataFrame with a fake
   "secret" column; assert the tool result contains only schema + ≤3 sample
   rows + stats, and the full 1000-row payload is **absent**.

## 9. Documentation

A short architecture note (docstring in `remote_exec_tool.py` plus this spec)
describing the spawn→execution path, the isolation guarantee, and the opt-in
network egress allowlist — satisfying §3.1's "document" requirement.

## 10. Out of Scope

- Persistent / reusable sandbox lifecycle tools (admin-gated today).
- microVM (Firecracker / gVisor) backend swap — current Docker sandbox retained;
  design stays backend-agnostic via `SandboxManager`.
- Egress credential proxy — noted as future work.

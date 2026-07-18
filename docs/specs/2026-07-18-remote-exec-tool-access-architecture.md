# remote_exec — Isolated Task-Agent Sandbox Access (Architecture Note)

## Spawn-to-Execution Path
Task Agent (3xxxx) → agent_orchestrator._execute_task_inner →
llm_client.generate_with_tools → LLM tool_call `remote_exec` →
ToolCreationService.execute_tool (auto-injects real `agent_id`) →
tool_registry → remote_exec_tool.execute → RemoteExecutorService.execute →
execution_guard.validate_code → SandboxManager.create_sandbox →
docker cp code/input/executor → docker exec python /tmp/executor.py →
executor.py analyzes → schema/stats/sample(≤3) → destroy_sandbox (finally) →
summary returned to agent.

## Sandbox Capability Posture
- Default-deny network (network_mode="none"); opt-in bridge with egress
  allowlist (private/IMDS/loopback blocked).
- Read-only rootfs + size-capped tmpfs `/tmp` (noexec,nosuid,nodev).
- Non-root `executor` user, all Linux capabilities dropped, no-new-privileges.
- CPU/mem capped; ephemeral (destroyed after each call).
- No host secrets/creds mounted into the sandbox.

## PII-Isolation Contract
The executor returns ONLY: output_schema, row_count, sample (≤3 rows, each
field ≤500 chars), stats, truncated stdout/stderr (≤1000 chars). The full raw
DataFrame / raw rows never serialize out of the container. The LLM reasons
about shape/schema, not content.

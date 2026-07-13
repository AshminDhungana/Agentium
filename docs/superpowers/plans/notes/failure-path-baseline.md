# Baseline Failure-Path Trace for Provider-Resilience Refactor

> **Purpose:** Document the *current* (pre-refactor) behaviour of the two disjoint LLM execution paths so that Tasks 12 and 23 can assert against these exact baselines.  
> **Scope:** `execute_task_async` (Celery worker path, **Path A**) and `AgentOrchestrator.execute_task` (API/WebSocket path, **Path B**).

---

## 1. Path A — Celery Worker (`execute_task_async`)

### 1.1 Call chain (file:line confirmed)

```
backend/services/tasks/task_executor.py:96
  @celery_app.task(name="agentium.tasks.task_executor.execute_task_async",
                   bind=True, max_retries=3)
  def execute_task_async(self, task_id, agent_id):
      ...
      result = agent.execute_with_skill_rag(task, db)           # line 122
backend/models/entities/agents.py:200
  def execute_with_skill_rag(self, task, db):
      ...
      result = await ModelService.generate_with_agent(...)     # line 78 in skill_rag.py
backend/services/skill_rag.py:78
  async def execute_with_skills(...):
      ...
      result = await ModelService.generate_with_agent(...)     # line 78
backend/services/model_provider.py:935
  @staticmethod
  async def generate_with_agent(...):
      provider = await ModelService.get_provider(...)          # line 916
      result = await provider.generate(...)                    # line 936
      # on exception: bare `raise` → bubbles verbatim
```

### 1.2 Exception handling inside the task (lines 177–233)

```python
except Exception as exc:
    logger.error(f"Task execution failed: {exc}")
    # Phase 13.4 Anti-Pattern Early Warning (vector search + websocket broadcast)
    ...
    countdown = min(2 ** self.request.retries, 60)
    logger.info(f"Retrying task {task_id} in {countdown}s (attempt {self.request.retries + 1})")
    raise self.retry(exc=exc, countdown=countdown)   # ← ONLY action
```

**Key observations:**
- The task **never** sets `Task.status = TaskStatus.FAILED` (line 46 in `task.py` exists but is never touched here).
- The task **never** creates an `AuditLog` entry on failure (the only audit logs are on success paths or in separate maintenance tasks).
- `self.retry(...)` is raised unconditionally; when `self.request.retries == max_retries (3)`, Celery marks the task as `RETRY` exhaustion but **leaves the DB row in `IN_PROGRESS`** (no terminal status transition).
- The Celery worker **does not crash/hang** — after `max_retries` the task ends in a non-terminal state and the worker picks up the next message.

---

## 2. Path B — API/WebSocket (`AgentOrchestrator.execute_task`)

### 2.1 Call chain (file:line confirmed)

```
backend/services/agent_orchestrator.py:94
  async def execute_task(self, task, agent, db):
      ...
      return await self._execute_task_inner(task, agent, db)  # line 115
backend/services/agent_orchestrator.py:208
  async def _execute_task_inner(...):
      llm_client = LLMClient(db=db)
      result = await llm_client.generate_with_tools(         # line 208
          agent=agent,
          user_message=task.description,
          db=db,
          config_id=config_id,
          system_prompt_override=system_prompt,
          agent_tier=tier_str,
          task_id=task.agentium_id,
          max_tool_iterations=10,
          max_tokens_multiplier=max_tokens_multiplier,
          chain_of_thought=requires_cot,
      )
backend/core/llm_client.py:227
  async def generate_with_tools(...):
      configs_to_try = [config_id] if config_id else []      # line 244
      # fallback_configs is accepted but NEVER passed by caller
      if not configs_to_try:
          configs_to_try = [agent.preferred_config_id] or [None]  # lines 250-254
      # → length of configs_to_try = 1 (single provider, no fallbacks)
      for attempt_config_id in configs_to_try:
          for attempt in range(_max_retries + 1):            # _max_retries defaults to 3
              try:
                  result = await ModelService.generate_with_agent_tools(...)
                  return result
              except Exception as exc:
                  last_error = exc
                  cb.record_failure()
                  if attempt < _max_retries and (is_rate_limit or self._is_retryable(exc)):
                      await self._delay(attempt)
                      continue
                  else:
                      break
      # Exhaustion → clean RuntimeError
      if last_error:
          raise RuntimeError(
              f"LLMClient.generate_with_tools exhausted all {len(configs_to_try)} provider(s) "
              f"and {_max_retries} retries. Last error: {last_error}"
          ) from last_error
```

### 2.2 Wrapping stall/retry loop in `execute_task` (lines 114–155)

```python
try:
    return await self._execute_task_inner(task, agent, db)
except StalledReasoningError as stall_exc:
    if resume_count >= 3:
        raise   # ← RuntimeError from LLMClient bubbles out here
    exec_ctx["stalled_resume_count"] = resume_count + 1
    task.execution_context = exec_ctx
    db.commit()
    agent.compress_ethos(db)
    return await self._execute_task_inner(task, agent, db, resume_hint=...)
```

**Key observations:**
- `configs_to_try` length is **exactly 1** — `fallback_configs` parameter exists on the method signature but is **never supplied** by `_execute_task_inner`.
- On provider exhaustion the `RuntimeError` **propagates cleanly** out of `execute_task`; Celery (if invoked via `delay()`) marks the task `FAILURE`, FastAPI returns 500.
- No `AuditLog` is written on this failure path.
- The stall/resume loop catches `StalledReasoningError` only — provider exhaustion is **not** caught and retried here.

---

## 3. Four Exhaustion Checks (code-reading verdict)

| Check | Path A (Celery) | Path B (API) | Verdict |
|-------|-----------------|--------------|---------|
| **(a) Worker crash / hang** | **NO** — after `max_retries` the task exits via `self.retry` exhaustion; worker stays alive and dequeues next message. | **NO** — `RuntimeError` propagates, Celery marks task `FAILURE`, worker continues. | Both paths: worker survives. |
| **(b) `Task.FAILED` status written** | **NO** — `TaskStatus.FAILED` (line 46 `task.py`) is never assigned; row remains `IN_PROGRESS`. | **NO** — exception bubbles before any status transition; task row stays `IN_PROGRESS` (or whatever it was). | **Gap:** neither path marks terminal failure. |
| **(c) `AuditLog` on failure** | **NO** — only success-path logs + anti-pattern warning (websocket/Redis, not `AuditLog`). | **NO** — no `AuditLog.log(...)` call in the exception chain. | **Gap:** no audit trail for provider exhaustion. |
| **(d) Worker picks up next task** | **YES** — Celery worker loop unaffected. | **YES** — FastAPI/Celery worker unaffected; next request/task processed normally. | Both paths: worker survives. |

> **This is the exact gap Task 12 (provider-resilience refactor) is designed to close:**  
> • Exhaustion → `TaskStatus.FAILED` + `AuditLog` (category `PROVIDER_EXHAUSTION`)  
> • Fallback provider chain (`fallback_configs` populated and honoured)  
> • Circuit-breaker-aware provider selection before first attempt.

---

## 4. Exact File:Line Citations for Future Assertions

| Behaviour | File | Lines |
|-----------|------|-------|
| Celery task decorator (`bind=True, max_retries=3`) | `backend/services/tasks/task_executor.py` | 96 |
| `execute_with_skill_rag` → `ModelService.generate_with_agent` | `backend/models/entities/agents.py` | 200–214 |
| `SkillRAG.execute_with_skills` → `ModelService.generate_with_agent` | `backend/services/skill_rag.py` | 78 |
| `ModelService.generate_with_agent` bare `raise` | `backend/services/model_provider.py` | 945 |
| Celery exception handler — only `self.retry` | `backend/services/tasks/task_executor.py` | 177–233 |
| `AgentOrchestrator.execute_task` stall loop | `backend/services/agent_orchestrator.py` | 114–155 |
| `_execute_task_inner` → `LLMClient.generate_with_tools` | `backend/services/agent_orchestrator.py` | 208 |
| `LLMClient.generate_with_tools` `configs_to_try` construction | `backend/core/llm_client.py` | 244–254 |
| Exhaustion `RuntimeError` raise | `backend/core/llm_client.py` | 307–314 |
| `TaskStatus.FAILED` enum exists but unused | `backend/models/entities/task.py` | 46 |
| `AuditLog` model import available | `backend/models/entities/audit.py` | — |

---

## 5. Hypothesis Confirmation

| Brief claim | Actual code finding | Match? |
|-------------|---------------------|--------|
| Path A: `execute_task_async` decorator `bind=True, max_retries=3`, manual `countdown=min(2**retries,60)` | ✅ Confirmed (lines 96, 231) | ✓ |
| Path A: only `raise self.retry(...)` on exception; no `Task.FAILED`, no `AuditLog` | ✅ Confirmed (lines 177–233) | ✓ |
| Path B: `AgentOrchestrator.execute_task` → `_execute_task_inner` → `LLMClient.generate_with_tools` | ✅ Confirmed (lines 94, 157, 208) | ✓ |
| Path B: `configs_to_try` length 1, `fallback_configs` never passed | ✅ Confirmed (lines 244–254, 208) | ✓ |
| Path B: exhaustion raises clean `RuntimeError`, wrapped by stall/resume loop | ✅ Confirmed (lines 307–314, 114–155) | ✓ |
| Four checks: (a) no worker hang, (b) no FAILED, (c) no AuditLog, (d) worker continues | ✅ All confirmed as estimated | ✓ |

**Conclusion:** The brief's expected conclusions are **fully verified** against current code. No surprises found.
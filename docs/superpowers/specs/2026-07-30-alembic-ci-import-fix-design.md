# CI Alembic Import Fix Design

## Problem

The GitHub Actions CI job `a11y-with-backend` (in workflow `integration-a11y.yml`) was failing during the alembic migration step with:

```
ModuleNotFoundError: No module named 'backend'
```

**Location:** `backend/models/entities/user_config.py:13` and `backend/models/entities/event_trigger.py:97,173`

## Root Cause

In CI, alembic runs from the `backend/` directory (see workflow line 91: `cd backend && alembic upgrade head`).

The alembic `env.py` adds `backend/` to `sys.path`:
```python
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # adds /backend
```

This allows relative imports like `from models.entities.base import Base` to work (since `models/` is a sibling of `alembic/` inside `backend/`).

However, two model files used **absolute imports** from the project root:
- `backend/models/entities/user_config.py:13` → `from backend.core.config import settings`
- `backend/models/entities/event_trigger.py:97,173` → `from backend.core.config import settings`

When running from `backend/`, Python cannot find the `backend` package (it would require the parent of `backend/` to be in `sys.path`).

## Solution

Changed the absolute imports to **relative imports** (using `...` to go up three levels from `backend/models/entities/` to reach `backend/`):

### Files Modified

1. **`backend/models/entities/user_config.py`** (line 13)
   ```python
   # Before
   from backend.core.config import settings
   
   # After
   from ...core.config import settings
   ```

2. **`backend/models/entities/event_trigger.py`** (lines 97, 173)
   ```python
   # Before
   from backend.core.config import settings
   
   # After
   from ...core.config import settings
   ```

## Why This Approach?

| Approach | Pros | Cons |
|----------|------|------|
| **A: Relative imports (chosen)** | Follows existing pattern in codebase (most model files use relative imports); no CI config changes needed | Requires understanding of module depth |
| B: Fix `sys.path` in alembic/env.py | More robust for alembic specifically | Only fixes alembic, not other entry points |
| C: Set `PYTHONPATH` in CI | Explicit about intent | Duplicates path logic; brittle if directory structure changes |
| D: `pip install -e .` in backend | Makes backend a proper package | Requires `pyproject.toml`/setup.py; more invasive |

**Chosen: A** — It's the minimal fix that follows existing conventions in the codebase. Other model files (e.g., `task.py`, `workflow.py`, `wait_condition.py`) already use relative imports for `backend.models.database` via `from ...models.database import get_db_context` or similar patterns.

## Scope

Only the **top-level module imports** in model entity files that run during alembic autogenerate/migration. Internal method-level imports (e.g., inside `_generate_task_id()`) remain as `from backend.models.database import ...` because:
- They execute at runtime, not module import time
- They run when the application is properly started with correct `PYTHONPATH`
- They don't affect alembic migration execution

## Testing

1. Run alembic migration locally from `backend/`:
   ```bash
   cd backend && alembic upgrade head
   ```

2. Verify CI passes on next push to main/develop.

## Rollback Plan

If issues arise, revert the two files to use `from backend.core.config import settings` and consider Approach B (fixing `sys.path` in `alembic/env.py`) as a follow-up.
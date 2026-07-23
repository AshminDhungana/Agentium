# Fix: test_constitution_persona.py — voter_agentium_id NOT NULL Violation

**Date:** 2026-07-23
**Author:** AI-assisted
**Status:** Draft

## Problem

5 ERRORs + 4 FAILUREs in `backend/tests/test_constitution_persona.py` during CI.

### Root Cause

The `head_agent` fixture (line 102-169) cleans up any prior `HeadOfCouncil` with
`agentium_id="00001"` that was committed by a previous test's genesis run
(`seeded_db` in `conftest.py`). After deleting the prior agent, autoflush (triggered
by the next query at line 109) tries to UPDATE the related `IndividualVote`
(genesis ratification vote, `voter_agentium_id="00001"`), setting
`voter_agentium_id=NULL` as part of SQLAlchemy's relationship maintenance
for the `back_populates="votes_cast"` / `back_populates="council_member"` link.
This violates the `NOT NULL` constraint on `voter_agentium_id`.

The genesis code at `initialization_service.py:761` already correctly sets
`voter_agentium_id="00001"`. The issue is entirely in the test fixture's cleanup
— deleting the parent Agent triggers ORM-level relationship maintenance that
attempts to nullify the child's reference column.

### Impact

- 5 ERRORs (all setup-phase: `head_agent` fixture raises during cleanup)
- 4 FAILUREs in tests that depend on `head_agent` (cascade from failed fixture)
- Total: 9 of 20 tests in the file affected

## Design

### Target

`backend/tests/test_constitution_persona.py` — the `head_agent` fixture and its
`finally` teardown block.

### Change 1: Explicitly delete related votes before agent deletion

Before `test_db.delete(prior)`, delete any `IndividualVote` rows that reference
the agent's `agentium_id`. Use `synchronize_session=False` to avoid loading
objects into the session:

```python
prior = test_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
if prior:
    test_db.query(IndividualVote).filter_by(
        voter_agentium_id="00001"
    ).delete(synchronize_session=False)
    test_db.delete(prior)
```

This prevents SQLAlchemy from ever loading IndividualVote objects into the
session with a stale `council_member` reference.

### Change 2: Wrap cleanup in `no_autoflush` block

Wrap the entire cleanup section in `with test_db.no_autoflush:` to prevent
premature flushes from triggering during query-based cleanup:

```python
with test_db.no_autoflush:
    prior = test_db.query(HeadOfCouncil)...first()
    if prior:
        test_db.query(IndividualVote).filter_by(...).delete(...)
        test_db.delete(prior)
    prior_ethos = test_db.query(Ethos)...first()
    ...
```

The actual flush happens explicitly at `test_db.commit()` (line 115), by which
point the votes are already deleted.

### Change 3: Apply same fix to `finally` teardown

The `finally` block (lines 159-168) also deletes the agent and could encounter
the same issue. Apply the same explicit vote deletion there.

### How the three changes interact

| Change | Purpose | Alone sufficient? |
|--------|---------|-------------------|
| 1 (explicit vote delete) | Removes the constraint-violating rows before cascade | Yes — removes root cause |
| 2 (no_autoflush guard) | Prevents premature flushes from any source | No — cascade still happens at commit |
| 3 (finally fix) | Same root cause in teardown | Yes — but only for teardown |

Both Change 1 and Change 3 address the root cause (objects being cascade-loaded);
Change 2 is a defense-in-depth guard.

### Non-goals

- Not changing the `IndividualVote` model (column stays NOT NULL — correct design)
- Not changing genesis vote creation (already correct)
- Not changing the `test_db` fixture or its transaction model

## Verification

After the fix, the 5 ERRORs and 4 FAILUREs in `test_constitution_persona.py`
should resolve to clean passes. Run:

```
pytest tests/test_constitution_persona.py -v
```

Expected: 20 passed, 0 failed, 0 errors.

No other files are modified, so no regression risk outside this file.

## Future

After this fix, re-assess the other 3 failing tests in the CI report
(`test_model_pricing`, `test_phase13_success_criteria`,
`test_workspace_persistence`) to determine if they are independent or
additional cascade effects.
# ADR-009: Standardised Error Response Envelope

## Status

Accepted (2026-07-01)

## Context

Every route and middleware in Agentium was raising bare `fastapi.HTTPException` with inconsistent response shapes — some returned `{"detail": ...}`, others added ad-hoc `{"code": ...}` fields. This made client-side error handling brittle and required endpoint-specific parsing.

## Decision

Adopt a single typed exception hierarchy (`AgentiumError`) in `backend/core/exceptions.py` and a single response envelope (`{error, code, detail}`) in `backend/core/error_responses.py`. A global `register_error_handlers(app)` call in `main.py` ensures every exception serialises identically.

## Consequences

- **Positive:**
  - Client consumers (SDK, frontend, third-party integrations) can rely on a stable error envelope.
  - Adding new error types is a one-line class definition.
  - Middleware no longer constructs ad-hoc dicts — they pass through the same helper.

- **Negative:**
  - Large mechanical refactor across 38 route files; risk of needing to catch and revert regressions.
  - `HTTPException` is still the base class, so FastAPI's built-in validation error responses (422) still return `{"detail": [...]}` — this is intentional and matches OpenAPI convention.

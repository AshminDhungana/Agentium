## Summary

Fixes the 180-second timeout in `test_default_admin_credentials_work` (and potentially other integration tests) caused by a thread-safety issue with SQLAlchemy sessions.

## Root Cause

The `client` fixture in `backend/tests/integration/conftest.py` used `TestClient(app)` which runs the ASGI app in a **background thread**. The fixture shared a single `db_session` across:
- The test thread (calling `create_default_admin(fresh_db)`)
- The TestClient's background thread (handling `client.post("/api/v1/auth/login")`)

SQLAlchemy sessions are **not thread-safe** - concurrent access from two threads caused a deadlock that timed out after 180 seconds (pytest-timeout).

## Fix

Replaced `TestClient` with `httpx.Client(transport=ASGITransport(app))` which executes requests in the **same thread** as the test, making shared session access safe and sequential.

```python
# Before (causes thread-safety issues):
test_client = TestClient(app)

# After (same-thread execution):
transport = ASGITransport(app=app)
test_client = httpx.Client(transport=transport, base_url="http://test")
```

## Testing

- The `async_client` fixture already used this correct pattern with `ASGITransport` + `httpx.AsyncClient`
- This change aligns the sync `client` fixture with the same safe approach
- WebSocket tests (`ws_client` fixture) still use `TestClient` as they require `websocket_connect` which isn't available in httpx
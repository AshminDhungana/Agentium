import os
from slowapi import Limiter
from slowapi.util import get_remote_address

# ── Phase 17.1 — slowapi limiter (Redis-backed for distributed correctness) ──
# get_remote_address reads X-Real-IP → X-Forwarded-For → request.client.host
# so it works correctly behind Nginx which sets X-Real-IP.
# In CI environments, use permissive limits to avoid false test failures.

_IS_CI_OR_TEST = os.getenv("CI", "false").lower() == "true" or os.getenv("TESTING", "false").lower() == "true"

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    default_limits=["99999999/minute"] if _IS_CI_OR_TEST else ["200/minute"],
)

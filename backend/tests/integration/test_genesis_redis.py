"""
Integration test for genesis Redis state persistence (Spec §1.3, P0).

Boots the genesis trigger against a REAL Redis instance and asserts that
the ``genesis:state`` key actually lands (was previously never awaited,
and the outer write referenced an undefined ``get_redis_client``).

Requires running services (Redis on REDIS_URL). Marked ``integration`` so
it is skipped in the unit suite; run via ``make test-integration``.
"""
import json

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from backend.services import initialization_service as init_svc
from backend.core.redis import get_redis_client


@pytest.mark.integration
async def test_genesis_state_persists_to_redis():
    # Only run against a reachable Redis — skip otherwise.
    try:
        probe = get_redis_client()
        await probe.ping()
    except Exception:
        pytest.skip("real Redis (REDIS_URL) not reachable")

    await probe.delete("genesis:state")

    fake_db = MagicMock()

    with patch.object(
        init_svc.InitializationService, "is_system_initialized", return_value=False
    ), patch.object(
        init_svc.InitializationService,
        "run_genesis_protocol",
        new=AsyncMock(return_value={"status": "complete", "message": "ok"}),
    ), patch.object(
        init_svc, "_replay_genesis_welcome", new=AsyncMock()
    ), patch(
        "backend.api.routes.websocket.manager", new=AsyncMock()
    ):
        triggered = init_svc.trigger_genesis_if_needed(fake_db)
        assert triggered is True
        # Let the background genesis task run to completion.
        await _await_genesis()

    raw = await probe.get("genesis:state")
    assert raw is not None, "genesis:state key was never written to Redis"
    state = json.loads(raw)
    assert state["phase"] in ("running", "complete")

    await probe.delete("genesis:state")


async def _await_genesis():
    """Yield control to the event loop so the scheduled genesis task runs."""
    import asyncio

    for _ in range(50):
        raw = await get_redis_client().get("genesis:state")
        if raw is not None:
            try:
                state = json.loads(raw)
                if state.get("phase") in ("complete", "failed"):
                    break
            except (TypeError, ValueError):
                pass
        await asyncio.sleep(0.1)

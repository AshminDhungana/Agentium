import pytest


def test_failure_simulator_fixture(failure_simulator):
    assert failure_simulator is not None
    assert hasattr(failure_simulator, "patch_http")
    assert hasattr(failure_simulator, "patch_db")


def test_circuit_breaker_inspector_fixture(circuit_breaker_inspector):
    assert circuit_breaker_inspector is not None
    assert hasattr(circuit_breaker_inspector, "get_state")


def test_ws_capture_fixture(ws_capture):
    assert ws_capture is not None
    assert hasattr(ws_capture, "captured_events")


@pytest.mark.asyncio
async def test_health_client_fixture(health_client):
    import sys
    print(f"health_client type: {type(health_client)}", file=sys.stderr)
    print(f"health_client dir: {[x for x in dir(health_client) if not x.startswith('_')]}", file=sys.stderr)
    assert health_client is not None
    assert hasattr(health_client, "get_degradation")
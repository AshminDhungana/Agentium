from backend.services.capability_registry import Capability, TIER_CAPABILITIES

def test_spawn_council_exists():
    assert Capability.SPAWN_COUNCIL.value == "spawn_council"

def test_spawn_council_granted_to_head():
    assert Capability.SPAWN_COUNCIL in TIER_CAPABILITIES["0"]

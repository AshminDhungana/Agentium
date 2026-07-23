"""
Verifies the nation name is persisted to the active Constitution and that a
second genesis run is a no-op (already_initialized) — i.e. "if the nation name
is there, genesis does not run again".
"""
import json
import pytest
from unittest.mock import patch

from backend.models.entities.constitution import Constitution
from backend.services.initialization_service import InitializationService


@pytest.mark.asyncio
async def test_genesis_saves_nation_name_and_skips_rerun(seeded_db):
    db = seeded_db
    with patch.object(
        InitializationService, "_has_any_active_api_key", return_value=True
    ):
        svc = InitializationService(db)
        r1 = await svc.run_genesis_protocol(force=True, country_name="Veridia")
        assert r1["country_name"] == "Veridia"

        const = db.query(Constitution).filter_by(is_active=True).first()
        assert const is not None
        prefs = json.loads(const.sovereign_preferences)
        assert prefs["country_name"] == "Veridia"

        # Re-run without force must NOT re-run / re-prompt.
        r2 = await svc.run_genesis_protocol()
        assert r2["status"] == "already_initialized"

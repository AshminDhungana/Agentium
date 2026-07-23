"""
Unit test for todo 4.1: the structural agents (Head/Council/Lead) must be
committed to the DB *before* the nation-naming step, so the chat WebSocket
handshake (which queries Head in a separate session) can see Head 00001 and
open the live chat during genesis instead of only after it fully completes.

This is exercised by stubbing the heavy structural/constitution steps and
asserting that ``db.commit()`` has already been called by the time
``_prompt_for_country_name`` runs.
"""
from unittest.mock import MagicMock, patch, AsyncMock

from backend.services import initialization_service
from backend.services.initialization_service import InitializationService


async def test_structural_commit_happens_before_naming_prompt():
    svc = InitializationService(db=MagicMock())

    captured = {}

    async def _fake_prompt(timeout=60):
        # Reached only after Head/Council/Lead are created. At this point the
        # early commit (todo 4.1) must have already flushed the structural
        # agents to the DB so other sessions can see Head 00001.
        captured["commit_called_before_prompt"] = svc.db.commit.called or svc.db.flush.called
        return None  # skip the 60s wait; use default name

    with patch.object(svc, "_has_any_active_api_key", return_value=True), \
         patch.object(svc, "_clear_existing_data", AsyncMock()), \
         patch.object(svc, "_create_head_of_council", AsyncMock(return_value=MagicMock())), \
         patch.object(svc, "_create_council_members", AsyncMock(return_value=[MagicMock(), MagicMock()])), \
         patch.object(svc, "_create_default_lead", AsyncMock(return_value=MagicMock())), \
         patch.object(svc, "_load_constitution", AsyncMock(return_value=MagicMock())), \
         patch.object(svc, "_vote_on_country_name", AsyncMock()), \
         patch.object(svc, "_notify_country_name_decision", AsyncMock()), \
         patch.object(svc, "_index_to_vector_db", AsyncMock()), \
         patch.object(svc, "_grant_council_privileges", AsyncMock()), \
         patch.object(svc, "_ensure_default_model_config", AsyncMock()), \
         patch.object(svc, "_prompt_for_country_name", _fake_prompt):
        await svc.run_genesis_protocol(force=True)

    assert captured.get("commit_called_before_prompt") is True


async def test_pre_prompt_failure_rolls_back_without_commit():
    """If structural creation fails before the naming step, genesis must not
    have committed (so a re-run can retry cleanly)."""
    svc = InitializationService(db=MagicMock())

    async def _boom():
        raise RuntimeError("head creation failed")

    with patch.object(svc, "_has_any_active_api_key", return_value=True), \
         patch.object(svc, "_clear_existing_data", AsyncMock()), \
         patch.object(svc, "_create_head_of_council", _boom):
        try:
            await svc.run_genesis_protocol(force=True)
        except Exception:
            pass

    assert svc.db.commit.called is False and svc.db.flush.called is False

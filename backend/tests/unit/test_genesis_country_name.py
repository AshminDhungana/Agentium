"""
Tests for the in-process country-name hand-off used by the genesis
set-country-name endpoint.
"""
import asyncio

from backend.services import initialization_service
from backend.services.initialization_service import (
    InitializationService,
    get_active_genesis,
    submit_country_name,
)


def test_no_active_genesis_returns_false():
    initialization_service._ACTIVE_GENESIS = None
    assert submit_country_name("Veridia") is False


def test_submit_delivers_name_to_awaiting_genesis():
    svc = InitializationService(db=None)
    svc._country_name_event = asyncio.Event()
    svc._pending_country_name = None
    svc.awaiting_country_name = True
    initialization_service._ACTIVE_GENESIS = svc
    try:
        assert submit_country_name("Veridia") is True
        assert svc._pending_country_name == "Veridia"
        assert svc._country_name_event.is_set()
    finally:
        initialization_service._ACTIVE_GENESIS = None


def test_get_active_genesis_returns_handle():
    svc = InitializationService(db=None)
    initialization_service._ACTIVE_GENESIS = svc
    try:
        assert get_active_genesis() is svc
    finally:
        initialization_service._ACTIVE_GENESIS = None

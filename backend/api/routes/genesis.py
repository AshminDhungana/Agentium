"""
Genesis API routes.

Handles:
- POST /api/v1/genesis/initialize    — run the Genesis Protocol
- POST /api/v1/genesis/country-name  — receive country name during genesis
- GET  /api/v1/genesis/status        — check whether genesis has run and an API key exists
"""

import asyncio
import logging
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.core.auth import get_current_user
from backend.services.initialization_service import InitializationService
from backend.services.api_key_manager import api_key_manager

router = APIRouter(prefix="/api/v1/genesis", tags=["genesis"])

logger = logging.getLogger(__name__)


@router.post("/initialize")
async def initialize_genesis(
    background_tasks: BackgroundTasks,
    country_name: str = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Trigger the Genesis Protocol to bootstrap the agent hierarchy.

    Idempotent — returns immediately if the system is already initialized.
    Requires at least one active API key to be configured; returns
    {"status": "no_api_key"} if none is found.

    The protocol runs in the background so the HTTP response is returned
    without waiting for the full bootstrap to complete (~5-15 seconds).
    The frontend should poll GET /status until it reports "ready".
    """
    service = InitializationService(db)

    if service.is_system_initialized():
        return {"status": "already_initialized", "message": "Genesis has already completed."}

    availability = api_key_manager.get_provider_availability(db)
    if not any(availability.values()):
        return {
            "status": "no_api_key",
            "message": "No active API key configured. Add a provider key first.",
        }

    # FIX (Bug 1): The background task must open its OWN database session.
    #
    # The original code passed the request's `db` session into the background
    # task. FastAPI keeps that session open for the entire lifetime of the task,
    # which means a single genesis run (up to 60 s country-name timeout + LLM
    # calls) holds one DB connection the whole time. With a typical pool of
    # 5-20 connections this starves every other request — including auth and
    # page-data fetches — causing all pages to hang at loading.
    #
    # The fix: capture only the plain values we need (country_name string) and
    # let the task create a fresh session from the pool, which it owns and
    # closes when it finishes. The request's `db` session is released normally
    # at the end of this handler function.
    _country_name = country_name  # capture primitive, not the session

    async def _run() -> None:
        # Import inside the task to avoid any module-level circular-import
        # issues; this path is only executed once per genesis run so the
        # overhead is negligible.
        from backend.models.database import get_db as _get_db  # noqa: PLC0415
        with next(_get_db()) as new_db:
            svc = InitializationService(new_db)
            try:
                await svc.run_genesis_protocol(country_name=_country_name)
            except Exception as exc:
                logger.error("Genesis Protocol failed: %s", exc, exc_info=True)

    background_tasks.add_task(_run)

    return {
        "status": "started",
        "message": "Genesis Protocol initiated. Poll GET /api/v1/genesis/status for progress.",
    }


@router.post("/country-name")
async def submit_country_name(
    name: str,
    db: Session = Depends(get_db),
):
    """
    Receive the sovereign's chosen country name during the genesis naming step.
    Called by the frontend when the user submits a name in response to the
    Head-of-Council broadcast prompt.
    """
    service = InitializationService(db)
    service.set_country_name(name)
    return {"status": "received", "name": name}


@router.get("/status")
async def genesis_status(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Check whether genesis has completed and whether at least one API key exists.

    Returns one of three states:
    - {"status": "no_api_key",  "initialized": bool}  — no healthy provider key
    - {"status": "pending",     "initialized": False}  — key exists but genesis not run
    - {"status": "ready",       "initialized": True}   — fully operational
    """
    service = InitializationService(db)
    is_initialized = service.is_system_initialized()

    availability = api_key_manager.get_provider_availability(db)
    has_key = any(availability.values())

    if not has_key:
        return {"status": "no_api_key", "initialized": is_initialized}
    if not is_initialized:
        return {"status": "pending", "initialized": False}
    return {"status": "ready", "initialized": True}
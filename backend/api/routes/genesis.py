"""
Genesis Protocol HTTP surface.

The nation-name prompt is broadcast in-process during genesis, but the chat
WebSocket is closed (1013) until Head 00001 exists, so the dashboard cannot
receive it. Instead the dashboard polls genesis-status and posts the chosen
name here.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.core.auth import get_current_user
from backend.services import initialization_service

router = APIRouter(tags=["genesis"])


class SetCountryNameRequest(BaseModel):
    name: str


class SetCountryNameResponse(BaseModel):
    accepted: bool
    reason: Optional[str] = None


@router.post("/genesis/set-country-name", response_model=SetCountryNameResponse)
async def set_country_name(
    payload: SetCountryNameRequest,
    current_user: dict = Depends(get_current_user),
) -> SetCountryNameResponse:
    """
    Submit the Sovereign's chosen nation name during Genesis.

    Returns accepted=false when genesis is not currently awaiting a name
    (already finished, not started, or past the prompt step).
    """
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nation name must not be empty.",
        )

    accepted = initialization_service.submit_country_name(name)
    if accepted:
        return SetCountryNameResponse(accepted=True)
    return SetCountryNameResponse(
        accepted=False,
        reason="Genesis is not currently awaiting a nation name.",
    )

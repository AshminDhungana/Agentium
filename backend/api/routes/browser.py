"""
Browser control REST endpoints — Phase 10.1.

Provides HTTP API for agents and the frontend to trigger
headless browser operations (navigate, scrape, screenshot, search).
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.routes.auth import get_current_active_user
from backend.models.database import get_db
from backend.models.entities.user import User
from backend.services.browser_service import get_browser_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/browser", tags=["Browser Control"])


# ── Request / Response Schemas ────────────────────────────────────────────────

class NavigateRequest(BaseModel):
    url: str = Field(..., description="URL to navigate to")
    agent_id: str = Field(default="system", description="Requesting agent ID")
    timeout_ms: Optional[int] = Field(default=None, description="Custom timeout in ms")


class ScrapeRequest(BaseModel):
    url: str = Field(..., description="URL to scrape")
    selector: Optional[str] = Field(default=None, description="CSS selector to target")
    agent_id: str = Field(default="system", description="Requesting agent ID")


class ScreenshotRequest(BaseModel):
    url: str = Field(..., description="URL to screenshot")
    agent_id: str = Field(default="system", description="Requesting agent ID")


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    agent_id: str = Field(default="system", description="Requesting agent ID")
    max_results: int = Field(default=5, ge=1, le=20, description="Max search results")


class URLCheckRequest(BaseModel):
    url: str = Field(..., description="URL to validate")


class ConfigureSessionRequest(BaseModel):
    fps: Optional[float] = None
    paused: Optional[bool] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/navigate")
async def navigate(
    req: NavigateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Navigate to a URL and return page title + status code."""
    svc = get_browser_service()
    result = await svc.navigate(req.url, agent_id=req.agent_id, timeout_ms=req.timeout_ms)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {
        "url": result.url,
        "title": result.title,
        "status_code": result.status_code,
    }


@router.post("/scrape")
async def scrape(
    req: ScrapeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Scrape page text/HTML, optionally targeting a CSS selector."""
    svc = get_browser_service()
    result = await svc.scrape(req.url, selector=req.selector, agent_id=req.agent_id)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {
        "url": result.url,
        "text": result.text,
        "html": result.html,
        "word_count": result.word_count,
    }


@router.post("/screenshot")
async def screenshot(
    req: ScreenshotRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Capture full-page screenshot (base64 PNG)."""
    svc = get_browser_service()
    result = await svc.screenshot(req.url, agent_id=req.agent_id, db=db)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {
        "url": result.url,
        "image_base64": result.image_base64,
        "content_type": result.content_type,
        "audit_log_id": result.audit_log_id,
    }


@router.post("/search")
async def search(
    req: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Perform a safe DuckDuckGo web search."""
    svc = get_browser_service()
    result = await svc.search(req.query, agent_id=req.agent_id, max_results=req.max_results)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {
        "query": result.query,
        "results": [
            {"title": r.title, "url": r.url, "snippet": r.snippet}
            for r in result.results
        ],
    }


@router.post("/check-url")
async def check_url(
    req: URLCheckRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Validate a URL against the safety guard (SSRF prevention)."""
    svc = get_browser_service()
    result = svc.check_url(req.url)
    return {
        "url": result.url,
        "safe": result.safe,
        "reason": result.reason,
    }


@router.get("/sessions")
async def get_sessions(
    current_user: User = Depends(get_current_active_user),
):
    """List all active browser sessions."""
    svc = get_browser_service()
    sessions = svc.get_all_sessions()
    return {
        "sessions": [
            {
                "task_id": s.session_id,
                "url": s.url,
                "title": s.title,
                "status": s.status,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "fps": s.fps
            }
            for s in sessions
        ]
    }


@router.get("/sessions/{task_id}/stream")
async def get_session_stream(
    task_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """Get the latest frame for a browser session (polling fallback)."""
    svc = get_browser_service()
    session = svc.get_session(task_id)
    if not session:
        raise HTTPException(status_code=404, detail="Browser session not found")
        
    return {
        "task_id": session.session_id,
        "frame": session.latest_frame,
        "url": session.url,
        "title": session.title,
        "status": session.status,
        "action_log": session.action_log[-50:],
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/sessions/{task_id}/configure")
async def configure_session(
    task_id: str,
    req: ConfigureSessionRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Configure stream settings."""
    svc = get_browser_service()
    session = svc.get_session(task_id)
    if not session:
        raise HTTPException(status_code=404, detail="Browser session not found")
        
    if req.fps is not None:
        session.fps = req.fps
    if req.paused is not None:
        session.status = "paused" if req.paused else "active"
        
    return {"status": "success"}
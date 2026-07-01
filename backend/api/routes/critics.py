"""
Critic API routes for Agentium.
Endpoints for submitting task outputs for critic review and querying review history.
"""

from fastapi import APIRouter, Depends, status, Query
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field

from backend.models.database import get_db
from backend.models.entities.critics import CriticType, CriticVerdict
from backend.services.critic_agents import critic_service
from backend.core.auth import get_current_active_user


router = APIRouter(prefix="/critics", tags=["critics"])


# ── Request / Response Schemas ──

class ReviewRequest(BaseModel):
    task_id: str = Field(..., description="ID of the task to review")
    output_content: str = Field(..., description="The output content to validate")
    critic_type: str = Field(..., description="Critic type: code, output, or plan")
    subtask_id: Optional[str] = Field(None, description="Optional subtask ID")
    retry_count: int = Field(0, ge=0, le=10, description="Current retry attempt")


# ── Endpoints ──

@router.post("/review")
async def submit_review(
    request: ReviewRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Submit a task output for critic review.
    
    Returns the critic's verdict (PASS / REJECT / ESCALATE),
    rejection reason if applicable, and retry guidance.
    """
    # Validate critic type
    try:
        critic_type = CriticType(request.critic_type.lower())
    except ValueError:
        raise BadRequestError(error=f"Invalid critic_type '{request.critic_type}'. Valid: {[ct.value for ct in CriticType]}", code="INVALID_CRITICTYPE_VALID")
    
    result = await critic_service.review_task_output(
        db=db,
        task_id=request.task_id,
        output_content=request.output_content,
        critic_type=critic_type,
        subtask_id=request.subtask_id,
        retry_count=request.retry_count,
    )
    
    return result


@router.get("/reviews/{task_id}")
async def get_task_reviews(
    task_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get all critic reviews for a specific task."""
    reviews = critic_service.get_reviews_for_task(db, task_id)
    return {"task_id": task_id, "reviews": reviews, "total": len(reviews)}


@router.get("/stats")
async def get_critic_stats(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get aggregate statistics for all critic agents."""
    return critic_service.get_critic_stats(db)

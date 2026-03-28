"""
Voting API routes for Agentium.
Handles constitutional amendment voting and task deliberations.

"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field

from backend.models.database import get_db
from backend.models.entities.voting import (
    AmendmentVoting, TaskDeliberation, IndividualVote,
    AmendmentStatus, DeliberationStatus, VoteType,
)
from backend.core.auth import get_current_active_user
from backend.services.amendment_service import AmendmentService

router = APIRouter(prefix="/voting", tags=["voting"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class AmendmentProposal(BaseModel):
    """Schema for proposing a new amendment."""
    title: str = Field(..., min_length=1, max_length=200)
    diff_markdown: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    voting_period_hours: Optional[int] = Field(default=48, ge=24, le=168)
    affected_articles: Optional[List[str]] = None


class VoteCast(BaseModel):
    """Schema for casting a vote."""
    vote: str = Field(..., pattern="^(for|against|abstain)$")
    rationale: Optional[str] = None


class AmendmentResponse(BaseModel):
    """Response schema for amendment."""
    id: str
    agentium_id: str
    status: str
    title: Optional[str] = None
    sponsors: List[str] = []
    sponsors_needed: int = 0
    eligible_voters: List[str] = []
    votes_for: int = 0
    votes_against: int = 0
    votes_abstain: int = 0
    final_result: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    created_at: Optional[str] = None
    discussion_thread: List[dict] = []


class DeliberationResponse(BaseModel):
    """Response schema for task deliberation."""
    id: str
    agentium_id: str
    task_id: str
    status: str
    participating_members: List[str] = []
    votes_for: int = 0
    votes_against: int = 0
    votes_abstain: int = 0
    final_decision: Optional[str] = None
    head_overridden: bool = False
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    time_limit_minutes: int = 30
    discussion_thread: List[dict] = []


class VoteResponse(BaseModel):
    """Response for cast vote."""
    amendment_id: Optional[str] = None
    deliberation_id: Optional[str] = None
    voter: str
    vote: str
    tally: dict


# ============================================================================
# Amendment Endpoints
# ============================================================================

@router.get("/amendments", response_model=List[AmendmentResponse])
async def list_amendments(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """List all amendment votings, optionally filtered by status."""
    query = db.query(AmendmentVoting)

    if status_filter:
        try:
            status_enum = AmendmentStatus(status_filter)
            query = query.filter(AmendmentVoting.status == status_enum)
        except ValueError:
            pass  # Ignore invalid status filter

    amendments = query.order_by(AmendmentVoting.created_at.desc()).limit(limit).all()

    # Extract titles from discussion threads
    result = []
    for a in amendments:
        title = None
        thread = a.discussion_thread or []
        for entry in thread:
            msg = entry.get("message", "")
            if msg.startswith("PROPOSAL:"):
                # Extract title from proposal message
                lines = msg.split("\n")
                if lines:
                    title = lines[0].replace("PROPOSAL:", "").strip()
                break

        sponsors = []
        for entry in thread:
            msg = entry.get("message", "")
            agent = entry.get("agent", "")
            if msg.startswith("PROPOSAL:") and agent and agent not in sponsors:
                sponsors.append(agent)
            elif msg.startswith("SPONSOR:") and agent and agent not in sponsors:
                sponsors.append(agent)

        result.append(AmendmentResponse(
            id=str(a.id),
            agentium_id=a.agentium_id,
            status=a.status.value,
            title=title,
            sponsors=sponsors,
            sponsors_needed=max(0, 2 - len(sponsors)),
            eligible_voters=a.eligible_voters or [],
            votes_for=a.votes_for,
            votes_against=a.votes_against,
            votes_abstain=a.votes_abstain,
            final_result=a.final_result,
            started_at=a.started_at.isoformat() if a.started_at else None,
            ended_at=a.ended_at.isoformat() if a.ended_at else None,
            created_at=a.created_at.isoformat() if a.created_at else None,
            discussion_thread=thread,
        ))

    return result


@router.post("/amendments", status_code=status.HTTP_201_CREATED)
async def propose_amendment(
    proposal: AmendmentProposal,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Propose a new constitutional amendment. Requires Council member."""
    user_id = str(current_user.get("sub", ""))

    try:
        service = AmendmentService(db)
        await service.initialize()

        result = await service.propose_amendment(
            proposer_id=user_id,
            title=proposal.title,
            diff_markdown=proposal.diff_markdown,
            rationale=proposal.rationale,
            voting_period_hours=proposal.voting_period_hours,
            affected_articles=proposal.affected_articles,
        )
        return result
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/amendments/{amendment_id}", response_model=dict)
async def get_amendment_details(
    amendment_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Get detailed information about an amendment."""
    service = AmendmentService(db)
    await service.initialize()

    detail = await service.get_amendment_detail(amendment_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Amendment not found")

    return detail


@router.post("/amendments/{amendment_id}/vote")
async def cast_amendment_vote(
    amendment_id: str,
    vote_data: VoteCast,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Cast a vote on an amendment."""
    user_id = str(current_user.get("sub", ""))

    try:
        vote_enum = VoteType(vote_data.vote)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid vote type")

    amendment = db.query(AmendmentVoting).filter_by(id=amendment_id).first()
    if not amendment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Amendment not found")

    if amendment.status != AmendmentStatus.VOTING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Amendment is not currently in VOTING status (current: {amendment.status.value})"
        )

    if user_id not in (amendment.eligible_voters or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not eligible to vote")

    try:
        vote_record = amendment.cast_vote(user_id, vote_enum, vote_data.rationale)
        db.commit()

        return VoteResponse(
            amendment_id=amendment_id,
            voter=user_id,
            vote=vote_data.vote,
            tally={
                "for": amendment.votes_for,
                "against": amendment.votes_against,
                "abstain": amendment.votes_abstain,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/amendments/{amendment_id}/sponsor")
async def sponsor_amendment(
    amendment_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Add sponsor to an amendment. Requires Council member."""
    user_id = str(current_user.get("sub", ""))

    try:
        service = AmendmentService(db)
        result = await service.sponsor_amendment(amendment_id, user_id)
        return result
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/amendments/{amendment_id}/start-voting")
async def start_amendment_voting(
    amendment_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Start voting on an amendment (transition from DELIBERATING to VOTING)."""
    service = AmendmentService(db)
    try:
        result = await service.start_voting(amendment_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/amendments/{amendment_id}/conclude")
async def conclude_amendment_voting(
    amendment_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Conclude voting on an amendment and execute the result."""
    service = AmendmentService(db)
    try:
        result = await service.conclude_voting(amendment_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============================================================================
# Task Deliberation Endpoints
# ============================================================================

@router.get("/deliberations", response_model=List[DeliberationResponse])
async def list_deliberations(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """List all task deliberations."""
    query = db.query(TaskDeliberation)

    if status_filter:
        try:
            status_enum = DeliberationStatus(status_filter)
            query = query.filter(TaskDeliberation.status == status_enum)
        except ValueError:
            pass

    deliberations = query.order_by(TaskDeliberation.created_at.desc()).limit(limit).all()

    result = []
    for d in deliberations:
        result.append(DeliberationResponse(
            id=str(d.id),
            agentium_id=d.agentium_id,
            task_id=d.task_id,
            status=d.status.value,
            participating_members=d.participating_members or [],
            votes_for=d.votes_for,
            votes_against=d.votes_against,
            votes_abstain=d.votes_abstain,
            final_decision=d.final_decision,
            head_overridden=d.head_overridden,
            started_at=d.started_at.isoformat() if d.started_at else None,
            ended_at=d.ended_at.isoformat() if d.ended_at else None,
            time_limit_minutes=d.time_limit_minutes,
            discussion_thread=d.discussion_thread or [],
        ))

    return result


@router.get("/deliberations/{deliberation_id}", response_model=dict)
async def get_deliberation_details(
    deliberation_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Get detailed information about a deliberation."""
    deliberation = db.query(TaskDeliberation).filter_by(id=deliberation_id).first()
    if not deliberation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deliberation not found")

    # Get individual votes
    votes = deliberation.individual_votes.all()

    return {
        "id": str(deliberation.id),
        "agentium_id": deliberation.agentium_id,
        "task_id": deliberation.task_id,
        "status": deliberation.status.value,
        "participating_members": deliberation.participating_members or [],
        "required_approvals": deliberation.required_approvals,
        "min_quorum": deliberation.min_quorum,
        "votes_for": deliberation.votes_for,
        "votes_against": deliberation.votes_against,
        "votes_abstain": deliberation.votes_abstain,
        "final_decision": deliberation.final_decision,
        "head_overridden": deliberation.head_overridden,
        "head_override_reason": deliberation.head_override_reason,
        "started_at": deliberation.started_at.isoformat() if deliberation.started_at else None,
        "ended_at": deliberation.ended_at.isoformat() if deliberation.ended_at else None,
        "time_limit_minutes": deliberation.time_limit_minutes,
        "discussion_thread": deliberation.discussion_thread or [],
        "individual_votes": [
            {
                "voter_id": v.voter_agentium_id,
                "vote": v.vote.value,
                "rationale": v.rationale,
                "changed_at": v.changed_at.isoformat() if v.changed_at else None,
            }
            for v in votes
        ],
    }


@router.post("/deliberations/{deliberation_id}/vote")
async def cast_deliberation_vote(
    deliberation_id: str,
    vote_data: VoteCast,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Cast a vote in a task deliberation.

    FIX: Now accepts both ACTIVE and QUORUM_REACHED statuses. The model's
    cast_vote() method supports voting in both states, but the old route
    only accepted ACTIVE, causing 400 errors when quorum was already reached.
    """
    user_id = str(current_user.get("sub", ""))

    try:
        vote_enum = VoteType(vote_data.vote)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid vote type")

    deliberation = db.query(TaskDeliberation).filter_by(id=deliberation_id).first()
    if not deliberation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deliberation not found")

    # FIX: Accept votes in both ACTIVE and QUORUM_REACHED states.
    # The TaskDeliberation.cast_vote() model method handles both statuses correctly.
    if deliberation.status not in (
        DeliberationStatus.ACTIVE,
        DeliberationStatus.QUORUM_REACHED,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Deliberation is not currently accepting votes "
                f"(current status: {deliberation.status.value}). "
                f"Voting is only open when status is 'active' or 'quorum'."
            ),
        )

    if user_id not in (deliberation.participating_members or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not part of this deliberation")

    try:
        vote_record = deliberation.cast_vote(user_id, vote_enum, vote_data.rationale)
        db.commit()

        return VoteResponse(
            deliberation_id=deliberation_id,
            voter=user_id,
            vote=vote_data.vote,
            tally={
                "for": deliberation.votes_for,
                "against": deliberation.votes_against,
                "abstain": deliberation.votes_abstain,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/deliberations/{deliberation_id}/start")
async def start_deliberation(
    deliberation_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Start a deliberation (transition from PENDING to ACTIVE)."""
    deliberation = db.query(TaskDeliberation).filter_by(id=deliberation_id).first()
    if not deliberation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deliberation not found")

    if deliberation.status != DeliberationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Deliberation must be in PENDING status (current: {deliberation.status.value})"
        )

    deliberation.start()
    db.commit()

    return {"status": deliberation.status.value, "started_at": deliberation.started_at.isoformat()}


@router.post("/deliberations/{deliberation_id}/conclude")
async def conclude_deliberation(
    deliberation_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Conclude a deliberation and calculate the result."""
    deliberation = db.query(TaskDeliberation).filter_by(id=deliberation_id).first()
    if not deliberation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deliberation not found")

    if deliberation.status not in [DeliberationStatus.ACTIVE, DeliberationStatus.QUORUM_REACHED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Deliberation must be ACTIVE or QUORUM_REACHED (current: {deliberation.status.value})"
        )

    try:
        result = deliberation.conclude()
        db.commit()
        return {
            "status": deliberation.status.value,
            "final_decision": deliberation.final_decision,
            "votes_for": deliberation.votes_for,
            "votes_against": deliberation.votes_against,
            "votes_abstain": deliberation.votes_abstain,
            "result": result,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
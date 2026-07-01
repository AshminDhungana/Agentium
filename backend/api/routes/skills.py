"""
REST API endpoints for skill management.
Supports both User (Sovereign) and Agent authentication.

"""

from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.models.entities.skill import SkillDB, SkillSubmission
from backend.models.entities.agents import Agent
from backend.models.entities.user import User
from backend.services.skill_manager import skill_manager
from backend.services.skill_rag import skill_rag
from backend.services.auth import get_current_agent as _get_agent_from_service

router = APIRouter(prefix="/skills", tags=["skills"])
security = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# Role → tier mapping (Fix 15)
# Covers all roles the frontend may store in user.role so that council / lead
# users receive correct backend privilege gates.
# ---------------------------------------------------------------------------
_ROLE_TO_TIER: dict[str, str] = {
    "primary_sovereign": "head",
    "deputy_sovereign":  "head",
    "sovereign":         "head",
    "admin":             "head",
    "council":           "council",
    "lead":              "lead",
    "user":              "task_agent",
}
_PRIVILEGED_TIERS = {"head", "council", "lead"}


async def get_current_user_or_agent(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> dict:
    """
    Unified authentication: accepts either a User JWT (Sovereign dashboard)
    or an Agent JWT.  Returns a normalised auth-context dict.
    """
    if not credentials:
        raise UnauthorizedError(error="Not authenticated", code="NOT_AUTHENTICATED", headers={"WWW-Authenticate": "Bearer"})

    token = credentials.credentials

    # ── Try User authentication first (Sovereign dashboard) ────────────────
    try:
        from jose import jwt
        from backend.core.config import settings

        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        username: str = payload.get("sub", "")
        if username:
            user = db.query(User).filter(User.username == username).first()
            if user and user.is_active:
                # Derive tier from the role field stored in the JWT / DB.
                # Fall back to is_admin for legacy tokens that predate roles.
                role: str = getattr(user, "role", None) or (
                    "admin" if user.is_admin else "user"
                )
                agent_tier = _ROLE_TO_TIER.get(role, "task_agent")
                return {
                    "type": "user",
                    "user": user,
                    "id": str(user.id),
                    "role": role,
                    "agent_tier": agent_tier,
                    "is_privileged": agent_tier in _PRIVILEGED_TIERS,
                    "identifier": user.username,
                }
    except Exception:
        pass  # Not a valid user token — fall through to agent auth

    # ── Try Agent authentication ────────────────────────────────────────────
    try:
        agent = await _get_agent_from_service(token, db)
        if agent and agent.status == "active":
            agent_tier = agent.agent_type.value
            return {
                "type": "agent",
                "agent": agent,
                "id": agent.id,
                "agentium_id": agent.agentium_id,
                "agent_type": agent_tier,
                "agent_tier": agent_tier,
                "is_privileged": agent_tier in _PRIVILEGED_TIERS,
                "identifier": agent.agentium_id,
            }
    except Exception:
        pass

    raise UnauthorizedError(error="Invalid token — not a valid User or Agent token", code="INVALID_TOKEN_NOT_A_VALID", headers={"WWW-Authenticate": "Bearer"})


# ---------------------------------------------------------------------------
# Request body schemas
# ---------------------------------------------------------------------------

class DeprecateRequest(BaseModel):
    """Body for POST /{skill_id}/deprecate (Fix 5)."""
    reason: str = "Deprecated"


class ReviewRequest(BaseModel):
    """Body for POST /submissions/{submission_id}/review."""
    decision: str           # "approve" | "reject"
    notes: Optional[str] = None


# ===========================================================================
# FIXED-PATH ROUTES — must appear before /{skill_id} routes (Fix 2)
# ===========================================================================

@router.get("/search")
async def search_skills(
    query: str = "",
    domain: Optional[str] = None,
    skill_type: Optional[str] = None,
    complexity: Optional[str] = None,
    creator_id: Optional[str] = None,       # Fix 4 — was silently ignored before
    min_success_rate: float = 0.0,
    n_results: int = 10,
    db: Session = Depends(get_db),
    auth_context: dict = Depends(get_current_user_or_agent),
):
    """
    Search skills with semantic query and optional filters.
    Works for both Sovereign (User) and Agent authentication.

    creator_id — when supplied, only results whose metadata.creator_id
    matches are returned.  Used by the frontend "My Submissions" tab.
    """
    filters: dict = {}
    if domain:
        filters["domain"] = domain
    if skill_type:
        filters["skill_type"] = skill_type
    if complexity:
        filters["complexity"] = complexity

    results = skill_manager.search_skills(
        query=query,
        agent_tier=auth_context["agent_tier"],
        db=db,
        filters=filters or None,
        n_results=n_results,
        min_success_rate=min_success_rate,
    )

    # Post-filter by creator_id when requested (Fix 4)
    if creator_id:
        results = [
            r for r in results
            if str(r.get("metadata", {}).get("creator_id", "")) == str(creator_id)
        ]

    return {
        "query": query,
        "results_count": len(results),
        "results": results,
    }


@router.get("/stats/popular")
async def get_popular_skills(
    domain: Optional[str] = None,
    limit: int = 10,
    db: Session = Depends(get_db),
    auth_context: dict = Depends(get_current_user_or_agent),
):
    """Get most used verified skills, ordered by usage count."""
    q = db.query(SkillDB).filter_by(verification_status="verified")
    if domain:
        q = q.filter_by(domain=domain)

    skills = q.order_by(SkillDB.usage_count.desc()).limit(limit).all()
    return {"skills": [s.to_dict() for s in skills]}


@router.get("/submissions/pending")
async def get_pending_submissions(
    db: Session = Depends(get_db),
    auth_context: dict = Depends(get_current_user_or_agent),
):
    """Get skill submissions pending Council review (privileged only)."""
    if not auth_context["is_privileged"]:
        raise ForbiddenError(error="Council/Head/Sovereign only", code="COUNCILHEADSOVEREIGN_ONLY")

    submissions = db.query(SkillSubmission).filter_by(status="pending").all()
    return {
        "count": len(submissions),
        "submissions": [
            {
                "submission_id": s.submission_id,
                "skill_id": s.skill_id,
                "submitted_by": s.submitted_by,
                "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
                "skill_data": s.skill_data,
            }
            for s in submissions
        ],
    }


@router.post("/submissions/{submission_id}/review")
async def review_submission(
    submission_id: str,
    body: ReviewRequest,
    db: Session = Depends(get_db),
    auth_context: dict = Depends(get_current_user_or_agent),
):
    """Review a skill submission — approve or reject (privileged only)."""
    if not auth_context["is_privileged"]:
        raise ForbiddenError(error="Council/Head/Sovereign only", code="COUNCILHEADSOVEREIGN_ONLY")

    submission = db.query(SkillSubmission).filter_by(
        submission_id=submission_id
    ).first()
    if not submission:
        raise NotFoundError(error="Submission not found", code="SUBMISSION_NOT_FOUND")

    skill_db = db.query(SkillDB).filter_by(skill_id=submission.skill_id).first()
    if not skill_db:
        raise NotFoundError(error="Skill not found", code="SKILL_NOT_FOUND")

    reviewer_id = (
        auth_context.get("agentium_id")
        or auth_context.get("identifier")
        or "unknown"
    )
    now = datetime.now(timezone.utc)   # Fix 13 — was datetime.utcnow()

    if body.decision == "approve":
        skill_db.verification_status = "verified"
        skill_db.verified_by = reviewer_id
        skill_db.verified_at = now
        submission.status = "approved"
    else:
        skill_db.verification_status = "rejected"
        skill_db.rejection_reason = body.notes or "Rejected"
        submission.status = "rejected"

    submission.reviewed_by = reviewer_id
    submission.reviewed_at = now        # Fix 13
    submission.review_notes = body.notes

    db.commit()

    return {
        "message": f"Submission {body.decision}d",
        "skill_id": submission.skill_id,
    }


@router.post("/")
async def create_skill(
    skill_data: dict,
    auto_verify: bool = False,
    db: Session = Depends(get_db),
    auth_context: dict = Depends(get_current_user_or_agent),
):
    """
    Create a new skill.
    Requires Council/Head review unless auto_verify=true (privileged only).
    """
    if auto_verify and not auth_context["is_privileged"]:
        raise ForbiddenError(error="Only Council/Head/Sovereign can auto-verify", code="ONLY_COUNCILHEADSOVEREIGN_CAN_AUTOVERIFY")

    creator = auth_context.get("agent")
    if not creator and auth_context["type"] == "user":
        creator = db.query(Agent).filter(Agent.agentium_id == "00001").first()

    if not creator:
        raise BadRequestError(error="Cannot determine skill creator", code="CANNOT_DETERMINE_SKILL_CREATOR")

    try:
        skill = skill_manager.create_skill(
            skill_data=skill_data,
            creator_agent=creator,
            db=db,
            auto_verify=auto_verify,
        )
        return {
            "message": "Skill created successfully",
            "skill_id": skill.skill_id,
            "status": skill.verification_status,
        }
    except Exception as exc:
        raise BadRequestError(error=str(exc), code="STREXC")


# ===========================================================================
# VARIABLE-PATH ROUTES — /{skill_id} must come after all fixed paths (Fix 2)
# ===========================================================================

@router.get("/{skill_id}/full")
async def get_skill_full(
    skill_id: str,
    db: Session = Depends(get_db),
    auth_context: dict = Depends(get_current_user_or_agent),
):
    """
    Get a skill with extended metadata:
      - submission_history
      - versions (all versions sharing the same skill_name, newest first)
      - stats
      - related_skills (same domain, top 5 by usage)
    """
    skill = skill_manager.get_skill_by_id(skill_id, db)
    if not skill:
        raise NotFoundError(error="Skill not found", code="SKILL_NOT_FOUND")

    if skill.verification_status != "verified" and not auth_context["is_privileged"]:
        raise ForbiddenError(error="Skill pending verification", code="SKILL_PENDING_VERIFICATION")

    skill_dict = skill.model_dump()

    skill_db = db.query(SkillDB).filter_by(skill_id=skill_id).first()

    # Submission history
    submissions = (
        db.query(SkillSubmission)
        .filter_by(skill_id=skill_id)
        .order_by(SkillSubmission.submitted_at.desc())
        .all()
    )
    skill_dict["submission_history"] = [
        {
            "submission_id": s.submission_id,
            "status": s.status,
            "submitted_by": s.submitted_by,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
            "reviewed_by": s.reviewed_by,
            "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None,
            "review_notes": s.review_notes,
        }
        for s in submissions
    ]

    if skill_db:
        # Fix 3 — was SkillDB.name (does not exist); correct column is skill_name
        versions = (
            db.query(SkillDB)
            .filter(SkillDB.skill_name == skill_db.skill_name)
            .order_by(SkillDB.created_at.desc())
            .all()
        )
        skill_dict["versions"] = [
            {
                "skill_id": v.skill_id,
                "verification_status": v.verification_status,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "verified_by": v.verified_by,
            }
            for v in versions
        ]

        skill_dict["stats"] = {
            "usage_count": skill_db.usage_count,
            "success_rate": skill_db.success_rate,
            "average_execution_time_ms": getattr(
                skill_db, "average_execution_time_ms", None
            ),
            "last_used_at": (
                skill_db.last_retrieved.isoformat()
                if getattr(skill_db, "last_retrieved", None)
                else None
            ),
        }

        related = (
            db.query(SkillDB)
            .filter(
                SkillDB.domain == skill_db.domain,
                SkillDB.skill_id != skill_id,
                SkillDB.verification_status == "verified",
            )
            .order_by(SkillDB.usage_count.desc())
            .limit(5)
            .all()
        )
        skill_dict["related_skills"] = [
            {
                "skill_id": r.skill_id,
                "name": r.display_name,
                "domain": r.domain,
                "usage_count": r.usage_count,
                "success_rate": r.success_rate,
            }
            for r in related
        ]

    return skill_dict


@router.get("/{skill_id}")
async def get_skill(
    skill_id: str,
    db: Session = Depends(get_db),
    auth_context: dict = Depends(get_current_user_or_agent),
):
    """Get skill details by ID."""
    skill = skill_manager.get_skill_by_id(skill_id, db)
    if not skill:
        raise NotFoundError(error="Skill not found", code="SKILL_NOT_FOUND")

    if skill.verification_status != "verified" and not auth_context["is_privileged"]:
        raise ForbiddenError(error="Skill pending verification", code="SKILL_PENDING_VERIFICATION")

    return skill.model_dump()


@router.post("/{skill_id}/deprecate")
async def deprecate_skill(
    skill_id: str,
    body: DeprecateRequest,          # Fix 5 — was a bare query-string param
    db: Session = Depends(get_db),
    auth_context: dict = Depends(get_current_user_or_agent),
):
    """
    Soft-delete a skill by marking it deprecated.
    Only the creator, privileged agents, or admin users may deprecate.
    """
    skill_db = db.query(SkillDB).filter_by(skill_id=skill_id).first()
    if not skill_db:
        raise NotFoundError(error="Skill not found", code="SKILL_NOT_FOUND")

    is_creator = str(skill_db.creator_id) == str(auth_context.get("id", ""))
    if not is_creator and not auth_context["is_privileged"]:
        raise ForbiddenError(error="Only the skill creator or privileged users may deprecate this skill", code="ONLY_THE_SKILL_CREATOR_OR")

    skill_db.verification_status = "deprecated"
    skill_db.rejection_reason = body.reason
    db.commit()

    return {
        "message": "Skill deprecated successfully",
        "skill_id": skill_id,
        "reason": body.reason,
    }


@router.post("/{skill_id}/update")
async def update_skill(
    skill_id: str,
    updates: dict,
    db: Session = Depends(get_db),
    auth_context: dict = Depends(get_current_user_or_agent),
):
    """Create a new version of an existing skill."""
    try:
        updater = auth_context.get("agent")
        if not updater and auth_context["type"] == "user":
            updater = db.query(Agent).filter(Agent.agentium_id == "00001").first()

        skill = skill_manager.update_skill(
            skill_id=skill_id,
            updates=updates,
            updater_agent=updater,
            db=db,
        )
        return {
            "message": "Skill updated",
            "skill_id": skill.skill_id,
            "new_version": skill.version,
        }
    except PermissionError as exc:
        raise ForbiddenError(error=str(exc), code="STREXC")
    except ValueError as exc:
        raise NotFoundError(error=str(exc), code="STREXC")


@router.post("/{skill_id}/execute")
async def execute_with_skill(
    skill_id: str,
    task_input: str,
    db: Session = Depends(get_db),
    auth_context: dict = Depends(get_current_user_or_agent),
):
    """Execute a task using a specific verified skill."""
    skill = skill_manager.get_skill_by_id(skill_id, db)
    if not skill:
        raise NotFoundError(error="Skill not found", code="SKILL_NOT_FOUND")

    if skill.verification_status != "verified":
        raise ForbiddenError(error="Skill not verified", code="SKILL_NOT_VERIFIED")

    agent = auth_context.get("agent")
    if not agent and auth_context["type"] == "user":
        agent = db.query(Agent).filter(Agent.agentium_id == "00001").first()

    if not agent:
        raise ForbiddenError(error="Execution requires agent context", code="EXECUTION_REQUIRES_AGENT_CONTEXT")

    result = await skill_rag.execute_with_skills(
        task_description=task_input,
        agent=agent,
        db=db,
    )
    return result
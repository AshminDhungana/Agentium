"""
Tool Creation API Routes — Phase 6.8

ROUTE ORDER RULE:
  Static routes (/deprecated, /analytics/*, /marketplace/*)
  must come BEFORE wildcard routes (/{tool_name}/*)
  or FastAPI will swallow them as tool_name values.

Fixes (Phase 6.8):
- VoteRequest.vote now validated as Literal["for", "against", "abstain"]
- /execute endpoint now enforces tier auth (blocks task agents 3xxxx)
  and injects agent_tier dependency to do so
- Router tag updated from stale "Phase 6.1" to "Phase 6.8"

Fixes (This Update):
- FinalizeImportRequest now includes listing_id field (was missing)
- finalize_import route now passes listing_id to service
"""
from fastapi import APIRouter, Depends, status
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal

from backend.models.database import get_db
from backend.core.auth import get_current_active_user, get_current_agent_tier, get_current_agent_id
from backend.models.schemas.tool_creation import ToolCreationRequest
from backend.services.tool_creation_service import ToolCreationService
from backend.services.tool_versioning import ToolVersioningService
from backend.services.tool_deprecation import ToolDeprecationService
from backend.services.tool_analytics import ToolAnalyticsService
from backend.services.tool_marketplace import ToolMarketplaceService

router = APIRouter(prefix="/tool-management", tags=["Tool Creation - Phase 6.8"])


# ── Tier helpers ───────────────────────────────────────────────────────────────

def _require_head_or_council(agent_tier: str):
    """Raise 403 if agent is not Head (0xxxx) or Council (1xxxx)."""
    if not (agent_tier.startswith("0") or agent_tier.startswith("1")):
        raise ForbiddenError(error=f"Agent tier '{agent_tier}' is not authorized. Head or Council required.", code="AGENT_TIER_IS_NOT_AUTHORIZED")

def _require_not_task_agent(agent_tier: str):
    """Raise 403 if agent is a Task agent (3xxxx) — they cannot create or manage tools."""
    if agent_tier.startswith("3"):
        raise ForbiddenError(error="Task agents (3xxxx) cannot create or manage tools.", code="TASK_AGENTS_3XXXX_CANNOT_CREATE")


# ═══════════════════════════════════════════════════════════════
# REQUEST SCHEMAS
# ═══════════════════════════════════════════════════════════════

class VoteRequest(BaseModel):
    # FIX: was `vote: str` with no validation — any string was accepted silently.
    # Now typed as Literal so FastAPI/Pydantic rejects invalid values at parse time
    # with a clear 422 error before the request reaches service logic.
    vote: Literal["for", "against", "abstain"]

class ProposeUpdateRequest(BaseModel):
    new_code: str
    change_summary: str

class ApproveUpdateRequest(BaseModel):
    pending_version_id: str
    approved_by_voting_id: Optional[str] = None

class RollbackRequest(BaseModel):
    target_version_number: int
    reason: str

class DeprecateRequest(BaseModel):
    reason: str
    replacement_tool_name: Optional[str] = None
    sunset_days: Optional[int] = None

class ScheduleSunsetRequest(BaseModel):
    sunset_days: int

class ForceSunsetRequest(BaseModel):
    force: bool = False

class RestoreRequest(BaseModel):
    reason: str

class ExecuteToolRequest(BaseModel):
    kwargs: Dict[str, Any] = Field(default_factory=dict)
    task_id: Optional[str] = None

class PublishListingRequest(BaseModel):
    tool_name: str
    display_name: str
    category: str
    tags: List[str] = Field(default_factory=list)

class ImportToolRequest(BaseModel):
    pass  # agent_id comes from JWT now

# FIX: Added listing_id field which was missing - this caused the finalize_import
# route to fail because the service expects both listing_id and staging_id
class FinalizeImportRequest(BaseModel):
    listing_id: str   # ← ADDED: was missing, required by service
    staging_id: str

class RateToolRequest(BaseModel):
    rating: float  # 1.0 - 5.0

class YankListingRequest(BaseModel):
    reason: str

class UpdateListingRequest(BaseModel):
    pass


# ═══════════════════════════════════════════════════════════════
# CORE — Propose, Vote, List
# ═══════════════════════════════════════════════════════════════

@router.post("/propose")
async def propose_tool(
    request: ToolCreationRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """
    Agent proposes a new tool.
    - Head (0xxxx): auto-approved and activated immediately
    - Council (1xxxx) / Lead (2xxxx): triggers Council vote
    - Task agents (3xxxx): blocked
    """
    _require_not_task_agent(agent_tier)

    # Override created_by with verified JWT identity — agents cannot spoof their ID
    request.created_by_agentium_id = agent_id

    service = ToolCreationService(db)
    result  = service.propose_tool(request)
    if not result.get("proposed") and "error" in result:
        raise BadRequestError(error=result["error"], code="RESULTERROR")
    return result


@router.get("/")
async def list_tools(
    status_filter: Optional[str] = None,
    authorized_for_tier: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
):
    """
    List all tools, optionally filtered by status or authorized tier.
    Task agents only see tools authorized for their tier.
    Head/Council see all.
    """
    service = ToolCreationService(db)

    # Task agents can only see tools they're authorized for
    if agent_tier.startswith("3"):
        authorized_for_tier = agent_tier

    return service.list_tools(status=status_filter, authorized_for_tier=authorized_for_tier)


# ═══════════════════════════════════════════════════════════════
# DEPRECATION — static routes (must be before /{tool_name}/*)
# ═══════════════════════════════════════════════════════════════

@router.get("/deprecated")
async def list_deprecated(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """List all deprecated and sunset tools."""
    service = ToolDeprecationService(db)
    return service.list_deprecated_tools()


@router.post("/run-sunset-cleanup")
async def run_sunset_cleanup(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
):
    """Trigger sunset cleanup manually. Head/Council only."""
    _require_head_or_council(agent_tier)
    service = ToolDeprecationService(db)
    return service.run_sunset_cleanup()


# ═══════════════════════════════════════════════════════════════
# ANALYTICS — static routes (must be before /{tool_name}/*)
# ═══════════════════════════════════════════════════════════════

@router.get("/analytics/report")
async def get_analytics_report(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
):
    """Full analytics report across all tools. Head/Council only."""
    _require_head_or_council(agent_tier)
    service = ToolAnalyticsService(db)
    return service.get_full_report(days=days)


@router.get("/analytics/errors")
async def get_recent_errors(
    tool_name: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
):
    """Recent failed tool calls. Head/Council only."""
    _require_head_or_council(agent_tier)
    service = ToolAnalyticsService(db)
    return service.get_recent_errors(tool_name=tool_name, limit=limit)


@router.get("/analytics/agent/{agentium_id}")
async def get_agent_tool_usage(
    agentium_id: str,
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """
    Which tools has an agent been using?
    Agents can only view their own usage. Head/Council can view any agent.
    """
    if agent_tier.startswith("3") and agentium_id != agent_id:
        raise ForbiddenError(error="Task agents can only view their own tool usage.", code="TASK_AGENTS_CAN_ONLY_VIEW")
    service = ToolAnalyticsService(db)
    return service.get_agent_tool_usage(agentium_id=agentium_id, days=days)


# ═══════════════════════════════════════════════════════════════
# MARKETPLACE — static routes (must be before /{tool_name}/*)
# ═══════════════════════════════════════════════════════════════

@router.post("/marketplace/publish")
async def publish_tool(
    body: PublishListingRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """Publish an activated tool to the marketplace. Head/Council only."""
    _require_head_or_council(agent_tier)
    service = ToolMarketplaceService(db)
    result  = service.publish_tool(
        tool_name=body.tool_name,
        display_name=body.display_name,
        category=body.category,
        tags=body.tags,
        published_by=agent_id,   # from JWT, not request body
    )
    if not result.get("published"):
        raise BadRequestError(error=result.get("error"), code="RESULTGETERROR")
    return result


@router.get("/marketplace")
async def browse_marketplace(
    category: Optional[str] = None,
    tags: Optional[str] = None,
    search: Optional[str] = None,
    include_remote: bool = True,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Browse marketplace listings. All authenticated agents can browse."""
    service  = ToolMarketplaceService(db)
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    return service.browse_marketplace(
        category=category,
        tags=tag_list,
        search_query=search,
        include_remote=include_remote,
        page=page,
        page_size=page_size,
    )


@router.post("/marketplace/{listing_id}/import")
async def import_tool(
    listing_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """Stage a marketplace tool for import. Head/Council only."""
    _require_head_or_council(agent_tier)
    service = ToolMarketplaceService(db)
    result  = service.import_tool(listing_id=listing_id, requested_by=agent_id)
    if not result.get("staged"):
        raise BadRequestError(error=result.get("error"), code="RESULTGETERROR")
    return result


# FIX: Added listing_id parameter to match service signature
@router.post("/marketplace/finalize-import")
async def finalize_import(
    body: FinalizeImportRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
):
    """Finalize a staged marketplace import. Head/Council only."""
    _require_head_or_council(agent_tier)
    service = ToolMarketplaceService(db)
    # FIX: Now passing listing_id which was previously missing
    result  = service.finalize_import(
        listing_id=body.listing_id,   # ← ADDED: was missing
        staging_id=body.staging_id,
    )
    if not result.get("finalized"):
        raise BadRequestError(error=result.get("error"), code="RESULTGETERROR")
    return result


@router.post("/marketplace/{listing_id}/rate")
async def rate_tool(
    listing_id: str,
    body: RateToolRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_id: str = Depends(get_current_agent_id),
):
    """Rate a marketplace tool listing (1.0 - 5.0). All agents can rate."""
    service = ToolMarketplaceService(db)
    result  = service.rate_tool(
        listing_id=listing_id,
        rated_by=agent_id,
        rating=body.rating,
    )
    if not result.get("rated"):
        raise BadRequestError(error=result.get("error"), code="RESULTGETERROR")
    return result


@router.post("/marketplace/{listing_id}/yank")
async def yank_listing(
    listing_id: str,
    body: YankListingRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """Retract a marketplace listing. Head or original publisher only."""
    _require_head_or_council(agent_tier)
    service = ToolMarketplaceService(db)
    result  = service.yank_listing(
        listing_id=listing_id,
        yanked_by=agent_id,
        reason=body.reason,
    )
    if not result.get("yanked"):
        raise BadRequestError(error=result.get("error"), code="RESULTGETERROR")
    return result


@router.post("/marketplace/{tool_name}/update-listing")
async def update_listing(
    tool_name: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """Refresh a marketplace listing to the tool's current active version. Head/Council only."""
    _require_head_or_council(agent_tier)
    service = ToolMarketplaceService(db)
    result  = service.update_listing(tool_name=tool_name, updated_by=agent_id)
    if not result.get("updated"):
        raise BadRequestError(error=result.get("error"), code="RESULTGETERROR")
    return result


# ═══════════════════════════════════════════════════════════════
# WILDCARD ROUTES — /{tool_name}/* must come LAST
# ═══════════════════════════════════════════════════════════════

@router.post("/{tool_name}/vote")
async def vote_on_tool(
    tool_name: str,
    body: VoteRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """Council member casts a vote on a pending tool proposal. Council only."""
    if not agent_tier.startswith("1"):
        raise ForbiddenError(error="Only Council members (1xxxx) can vote on tool proposals.", code="ONLY_COUNCIL_MEMBERS_1XXXX_CAN")
    service = ToolCreationService(db)
    result  = service.vote_on_tool(tool_name, agent_id, body.vote)
    if not result.get("voted"):
        raise BadRequestError(error=result.get("error"), code="RESULTGETERROR")
    return result


@router.post("/{tool_name}/execute")
async def execute_tool(
    tool_name: str,
    body: ExecuteToolRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    # FIX: agent_tier was missing — any authenticated agent (including task agents 3xxxx)
    # could call this endpoint and bypass registry-level tier enforcement.
    # Now we inject agent_tier and block task agents explicitly.
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """
    Execute a registered tool with analytics recording.
    Note: for normal tool execution prefer POST /tools/execute which has
    full tier enforcement via the tool registry. This endpoint is for
    tools created via the tool creation workflow.

    Access: Head (0xxxx), Council (1xxxx), Lead (2xxxx) only.
    Task agents (3xxxx) must go through the standard /tools/execute route
    where per-tool tier authorization is checked against the registry.
    """
    _require_not_task_agent(agent_tier)
    service = ToolCreationService(db)
    return service.execute_tool(tool_name, agent_id, body.kwargs, body.task_id)


@router.get("/{tool_name}/analytics")
async def get_tool_analytics(
    tool_name: str,
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
):
    """Per-tool analytics. Head/Council only."""
    _require_head_or_council(agent_tier)
    service = ToolAnalyticsService(db)
    return service.get_tool_stats(tool_name=tool_name, days=days)


@router.post("/{tool_name}/deprecate")
async def deprecate_tool(
    tool_name: str,
    body: DeprecateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """Soft-deprecate a tool. Still callable but marked deprecated. Head/Council only."""
    _require_head_or_council(agent_tier)
    service = ToolDeprecationService(db)
    result  = service.deprecate_tool(
        tool_name=tool_name,
        deprecated_by=agent_id,
        reason=body.reason,
        replacement_tool_name=body.replacement_tool_name,
        sunset_days=body.sunset_days,
    )
    if not result.get("deprecated"):
        raise BadRequestError(error=result.get("error"), code="RESULTGETERROR")
    return result


@router.post("/{tool_name}/schedule-sunset")
async def schedule_sunset(
    tool_name: str,
    body: ScheduleSunsetRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """Schedule hard-removal date (minimum 7 days). Head/Council only."""
    _require_head_or_council(agent_tier)
    service = ToolDeprecationService(db)
    result  = service.schedule_sunset(
        tool_name=tool_name,
        requested_by=agent_id,
        sunset_days=body.sunset_days,
    )
    if not result.get("scheduled"):
        raise BadRequestError(error=result.get("error"), code="RESULTGETERROR")
    return result


@router.post("/{tool_name}/execute-sunset")
async def execute_sunset(
    tool_name: str,
    body: ForceSunsetRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """Hard-remove a tool. Requires sunset date passed (or Head force). Head only for force."""
    _require_head_or_council(agent_tier)
    service  = ToolDeprecationService(db)
    forced   = agent_id if body.force and agent_tier.startswith("0") else None
    result   = service.execute_sunset(tool_name=tool_name, forced_by=forced)
    if not result.get("executed"):
        raise BadRequestError(error=result.get("error"), code="RESULTGETERROR")
    return result


@router.post("/{tool_name}/restore")
async def restore_tool(
    tool_name: str,
    body: RestoreRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """Restore a deprecated tool to active. Head/Council only."""
    _require_head_or_council(agent_tier)
    service = ToolDeprecationService(db)
    result  = service.restore_tool(
        tool_name=tool_name,
        restored_by=agent_id,
        reason=body.reason,
    )
    if not result.get("restored"):
        raise BadRequestError(error=result.get("error"), code="RESULTGETERROR")
    return result


@router.post("/{tool_name}/versions/propose-update")
async def propose_tool_update(
    tool_name: str,
    body: ProposeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """Propose a code update to an existing tool. Head/Council/Lead only."""
    _require_not_task_agent(agent_tier)
    service = ToolVersioningService(db)
    result  = service.propose_update(
        tool_name=tool_name,
        new_code=body.new_code,
        change_summary=body.change_summary,
        proposed_by=agent_id,
    )
    if not result.get("proposed"):
        raise BadRequestError(error=result.get("error"), code="RESULTGETERROR")
    return result


@router.post("/{tool_name}/versions/approve-update")
async def approve_tool_update(
    tool_name: str,
    body: ApproveUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
):
    """Approve and activate a pending tool version. Head/Council only."""
    _require_head_or_council(agent_tier)
    service = ToolVersioningService(db)
    result  = service.approve_update(
        tool_name=tool_name,
        pending_version_id=body.pending_version_id,
        approved_by_voting_id=body.approved_by_voting_id,
    )
    if not result.get("approved"):
        raise BadRequestError(error=result.get("error"), code="RESULTGETERROR")
    return result


@router.post("/{tool_name}/versions/rollback")
async def rollback_tool(
    tool_name: str,
    body: RollbackRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """Roll back a tool to a specific prior version. Head/Council only."""
    _require_head_or_council(agent_tier)
    service = ToolVersioningService(db)
    result  = service.rollback(
        tool_name=tool_name,
        target_version_number=body.target_version_number,
        requested_by=agent_id,
        reason=body.reason,
    )
    if not result.get("rolled_back"):
        raise BadRequestError(error=result.get("error"), code="RESULTGETERROR")
    return result


@router.get("/{tool_name}/versions/changelog")
async def get_changelog(
    tool_name: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Get full version history and changelog for a tool."""
    service = ToolVersioningService(db)
    return service.get_changelog(tool_name)


@router.get("/{tool_name}/versions/diff")
async def get_version_diff(
    tool_name: str,
    version_a: int,
    version_b: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
):
    """Get a unified diff between two versions. Head/Council only."""
    _require_head_or_council(agent_tier)
    service = ToolVersioningService(db)
    result  = service.get_diff(tool_name, version_a, version_b)
    if "error" in result:
        raise NotFoundError(error=result["error"], code="RESULTERROR")
    return result
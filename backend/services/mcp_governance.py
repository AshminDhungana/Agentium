"""
MCP Governance Service — Phase 6.7
Brings MCP tools into Agentium's democratic approval model.

Philosophy: "Rowboat connects MCP tools directly. Agentium connects them through the Constitution."

Every tool invocation is:
  1. Checked against the Constitutional tier (forbidden → always block)
  2. Checked for required approval tokens (restricted → Head approval required)
  3. Executed via MCPClient
  4. Appended to the tool's persistent audit_log
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.models.entities.mcp_tool import MCPTool
from backend.services.mcp_client import MCPClient, MCPConnectionError

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# After this many consecutive failures the tool is auto-disabled
AUTO_DISABLE_THRESHOLD = 5

TIER_PRE_APPROVED = "pre_approved"
TIER_RESTRICTED   = "restricted"
TIER_FORBIDDEN    = "forbidden"

STATUS_PENDING  = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_REVOKED  = "revoked"
STATUS_DISABLED = "disabled"


# ── Verdict enum (mirrors constitutional_guard pattern) ───────────────────────

class MCPVerdict:
    ALLOW          = "allow"
    BLOCK          = "block"
    VOTE_REQUIRED  = "vote_required"
    HEAD_REQUIRED  = "head_required"


# ── Service ───────────────────────────────────────────────────────────────────

class MCPGovernanceService:
    """
    Centralises all MCP governance operations:
    - Proposal and Council approval workflow
    - Constitutional tier enforcement
    - Execution with full audit logging
    - Health monitoring and auto-disable
    """

    def __init__(self, db: Session):
        self.db = db

    # ══════════════════════════════════════════════════════════════════════════
    # PROPOSAL / APPROVAL / REVOCATION
    # ══════════════════════════════════════════════════════════════════════════

    def propose_mcp_server(
        self,
        *,
        name: str,
        description: str,
        server_url: str,
        tier: str,
        proposed_by: str,
        constitutional_article: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
    ) -> MCPTool:
        """
        Council member proposes a new MCP server for review.
        Creates the MCPTool record in 'pending' state.
        A Council vote must follow before the tool becomes usable.
        """
        if tier not in (TIER_PRE_APPROVED, TIER_RESTRICTED, TIER_FORBIDDEN):
            raise ValueError(f"Invalid tier '{tier}'. Must be pre_approved, restricted, or forbidden.")

        existing = self.db.query(MCPTool).filter_by(server_url=server_url).first()
        if existing:
            raise ValueError(f"MCP server '{server_url}' is already registered as '{existing.name}'.")

        tool = MCPTool(
            name=name,
            description=description,
            server_url=server_url,
            tier=tier,
            constitutional_article=constitutional_article,
            capabilities=capabilities or [],
            status=STATUS_PENDING,
            proposed_by=proposed_by,
            proposed_at=datetime.utcnow(),
            audit_log=[],
            approved_by_council=False,
            failure_count=0,
            consecutive_failures=0,
            usage_count=0,
            health_status="unknown",
            is_active=True,
        )
        self.db.add(tool)
        self.db.commit()
        self.db.refresh(tool)
        logger.info("[MCPGovernance] Tool proposed: %s (tier=%s) by %s", name, tier, proposed_by)
        return tool

    def approve_mcp_server(
        self,
        tool_id: str,
        *,
        approved_by: str,
        vote_id: Optional[str] = None,
    ) -> MCPTool:
        """
        Record Council approval after a successful vote.
        Moves the tool from 'pending' → 'approved'.
        Forbidden-tier tools can never be approved.
        """
        tool = self._get_tool_or_404(tool_id)

        if tool.tier == TIER_FORBIDDEN:
            raise PermissionError("Forbidden-tier tools cannot be approved — they are constitutionally banned.")

        if tool.status not in (STATUS_PENDING, STATUS_REJECTED):
            raise ValueError(f"Tool is in '{tool.status}' state and cannot be approved.")

        tool.status = STATUS_APPROVED
        tool.approved_by_council = True
        tool.approved_by = approved_by
        tool.approval_vote_id = vote_id
        tool.approved_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(tool)
        logger.info("[MCPGovernance] Tool approved: %s by %s (vote=%s)", tool.name, approved_by, vote_id)
        return tool

    def revoke_mcp_tool(
        self,
        tool_id: str,
        *,
        revoked_by: str,
        reason: str,
    ) -> MCPTool:
        """
        Emergency revocation — no vote required.
        Tool becomes immediately unavailable (checked at execution time).
        Cache invalidation is guaranteed: status checked on every call.
        """
        tool = self._get_tool_or_404(tool_id)
        tool.status = STATUS_REVOKED
        tool.revoked_by = revoked_by
        tool.revoked_at = datetime.utcnow()
        tool.revocation_reason = reason
        self.db.commit()
        self.db.refresh(tool)
        logger.warning("[MCPGovernance] Tool REVOKED: %s by %s — %s", tool.name, revoked_by, reason)
        return tool

    # ══════════════════════════════════════════════════════════════════════════
    # CONSTITUTIONAL TIER ENFORCEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def check_tier_access(
        self,
        tool_tier: str,
        agent_tier: str,
        has_head_approval_token: bool = False,
    ) -> str:
        """
        Returns an MCPVerdict constant.

        Tier 3 / forbidden  → always BLOCK regardless of who asks
        Tier 2 / restricted → ALLOW only with Head approval token; else HEAD_REQUIRED
        Tier 1 / pre_approved → ALLOW for any approved agent
        """
        if tool_tier == TIER_FORBIDDEN:
            return MCPVerdict.BLOCK

        if tool_tier == TIER_RESTRICTED:
            if has_head_approval_token:
                return MCPVerdict.ALLOW
            # Council members (1xxxx) and above can request approval
            if agent_tier.startswith("0") or agent_tier.startswith("1"):
                return MCPVerdict.HEAD_REQUIRED
            return MCPVerdict.BLOCK

        # pre_approved — open to any approved agent tier
        return MCPVerdict.ALLOW

    # ══════════════════════════════════════════════════════════════════════════
    # EXECUTION
    # ══════════════════════════════════════════════════════════════════════════

    async def execute_mcp_tool(
        self,
        tool_id: str,
        *,
        agent_id: str,
        agent_tier: str,
        params: Dict[str, Any],
        has_head_approval_token: bool = False,
        tool_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute an MCP tool through the full governance pipeline:
        1. Load and validate tool state (approved, not revoked/disabled)
        2. Constitutional Guard tier check
        3. Execute via MCPClient
        4. Append to audit_log
        5. Update health counters
        """
        tool = self._get_tool_or_404(tool_id)

        # ── State guard ────────────────────────────────────────────────────────
        if tool.status != STATUS_APPROVED:
            return self._blocked_response(tool.name, f"Tool status is '{tool.status}' — not approved for use.")

        # ── Constitutional Guard ───────────────────────────────────────────────
        verdict = self.check_tier_access(tool.tier, agent_tier, has_head_approval_token)

        if verdict == MCPVerdict.BLOCK:
            self._audit(tool, agent_id, params, success=False, error="Constitutional block — tier forbidden")
            return self._blocked_response(tool.name, "Constitutionally blocked. This tool tier is not permitted.")

        if verdict == MCPVerdict.HEAD_REQUIRED:
            return {
                "success": False,
                "tool": tool.name,
                "error": "Head of Council approval token required for restricted-tier tool.",
                "verdict": MCPVerdict.HEAD_REQUIRED,
            }

        # ── Execute ────────────────────────────────────────────────────────────
        target_tool = tool_name or (tool.capabilities[0] if tool.capabilities else tool.name)

        try:
            async with MCPClient(tool.server_url) as client:
                result = await client.call_tool(target_tool, params)

            # Update health counters on success
            tool.consecutive_failures = 0
            tool.health_status = "healthy"

        except MCPConnectionError as exc:
            result = {
                "success": False,
                "tool": target_tool,
                "error": str(exc),
                "timestamp": datetime.utcnow().isoformat(),
            }
            self._record_failure(tool)

        except Exception as exc:
            result = {
                "success": False,
                "tool": target_tool,
                "error": f"Unexpected error: {exc}",
                "timestamp": datetime.utcnow().isoformat(),
            }
            self._record_failure(tool)

        # ── Audit ──────────────────────────────────────────────────────────────
        self._audit(tool, agent_id, params, success=result.get("success", False), error=result.get("error"))

        # Update usage stats
        tool.usage_count = (tool.usage_count or 0) + 1
        tool.last_used_at = datetime.utcnow()
        self.db.commit()

        return result

    # ══════════════════════════════════════════════════════════════════════════
    # HEALTH MONITORING
    # ══════════════════════════════════════════════════════════════════════════

    async def get_tool_health(self, tool_id: str) -> Dict[str, Any]:
        """Ping the MCP server and record health status."""
        tool = self._get_tool_or_404(tool_id)

        client = MCPClient(tool.server_url)
        health = await client.health_check()

        tool.health_status = "healthy" if health["healthy"] else "down"
        tool.last_health_check_at = datetime.utcnow()
        if not health["healthy"]:
            self._record_failure(tool)
        else:
            tool.consecutive_failures = 0

        self.db.commit()
        return {**health, "tool_id": str(tool.id), "tool_name": tool.name}

    def auto_disable_on_failures(self, tool_id: str) -> bool:
        """
        Disable tool if consecutive failures exceed the threshold.
        Returns True if the tool was disabled.
        """
        tool = self._get_tool_or_404(tool_id)
        if tool.consecutive_failures >= AUTO_DISABLE_THRESHOLD:
            tool.status = STATUS_DISABLED
            tool.health_status = "down"
            self.db.commit()
            logger.error(
                "[MCPGovernance] Tool auto-disabled after %d consecutive failures: %s",
                tool.consecutive_failures, tool.name,
            )
            return True
        return False

    # ══════════════════════════════════════════════════════════════════════════
    # QUERIES
    # ══════════════════════════════════════════════════════════════════════════

    def get_approved_tools(self, agent_tier: Optional[str] = None) -> List[MCPTool]:
        """
        Return all approved tools, optionally filtered to those accessible
        by the given agent tier (forbidden tools are never returned).
        """
        query = self.db.query(MCPTool).filter(
            MCPTool.status == STATUS_APPROVED,
            MCPTool.tier != TIER_FORBIDDEN,
            MCPTool.is_active == True,
        )
        tools = query.order_by(MCPTool.name).all()

        if agent_tier and (agent_tier.startswith("2") or agent_tier.startswith("3")):
            # Lead and Task agents cannot access restricted tools
            tools = [t for t in tools if t.tier == TIER_PRE_APPROVED]

        return tools

    def list_all_tools(
        self,
        *,
        status: Optional[str] = None,
        tier: Optional[str] = None,
    ) -> List[MCPTool]:
        """Admin view — returns all tools regardless of status."""
        query = self.db.query(MCPTool).filter(MCPTool.is_active == True)
        if status:
            query = query.filter(MCPTool.status == status)
        if tier:
            query = query.filter(MCPTool.tier == tier)
        return query.order_by(MCPTool.name).all()

    def get_tool_audit_log(self, tool_id: str, limit: int = 100) -> List[dict]:
        """Return the last N audit entries for a tool."""
        tool = self._get_tool_or_404(tool_id)
        log = tool.audit_log or []
        return log[-limit:]

    # ══════════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _get_tool_or_404(self, tool_id: str) -> MCPTool:
        tool = self.db.query(MCPTool).filter(MCPTool.id == tool_id).first()
        if not tool:
            raise ValueError(f"MCP tool '{tool_id}' not found.")
        return tool

    def _audit(
        self,
        tool: MCPTool,
        agent_id: str,
        params: Dict[str, Any],
        *,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """Append one entry to the tool's persistent audit_log JSON column."""
        entry = {
            "agent_id": agent_id,
            "timestamp": datetime.utcnow().isoformat(),
            "input_hash": MCPClient.hash_params(params),
            "success": success,
        }
        if error:
            entry["error"] = error

        current_log = list(tool.audit_log or [])
        current_log.append(entry)
        # Prevent unbounded growth — keep last 1000 entries in DB column
        tool.audit_log = current_log[-1000:]

    def _record_failure(self, tool: MCPTool) -> None:
        tool.failure_count = (tool.failure_count or 0) + 1
        tool.consecutive_failures = (tool.consecutive_failures or 0) + 1
        tool.health_status = "degraded" if tool.consecutive_failures < AUTO_DISABLE_THRESHOLD else "down"
        self.auto_disable_on_failures(str(tool.id))

    @staticmethod
    def _blocked_response(tool_name: str, reason: str) -> Dict[str, Any]:
        return {
            "success": False,
            "tool": tool_name,
            "error": reason,
            "verdict": MCPVerdict.BLOCK,
            "timestamp": datetime.utcnow().isoformat(),
        }
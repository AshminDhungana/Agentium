"""
Tool Creation Service
Agent-initiated tool creation with democratic approval workflow.

Changes from original:
- ToolStaging moved to models/entities/tool_staging.py
- activate_tool() now creates initial ToolVersion via ToolVersioningService
- All tool calls wrapped with ToolAnalyticsService recording

Fixes (Phase 6.8):
- list_tools: safe JSON parse guard — to_dict() may return request_json as dict or str
- propose_tool: removed unused `persistent_council` import inside the method body
- persistent_council import removed from propose_tool (was imported but never called)
"""
from sqlalchemy.orm import Session
from backend.models.database import get_db_context
from backend.models.schemas.tool_creation import ToolCreationRequest
from backend.models.entities.tool_staging import ToolStaging
from backend.models.entities.voting import AmendmentVoting, AmendmentStatus
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.services.tool_factory import ToolFactory
from backend.services.tool_versioning import ToolVersioningService
from backend.services.tool_analytics import ToolAnalyticsService
from backend.core.tool_registry import tool_registry
from backend.models.entities.agents import Agent
from typing import Dict, Any, List, Optional
from datetime import datetime
import json


class ToolCreationService:
    """
    Service layer for agent-initiated tool creation with democratic approval.

    Responsibilities:
      - Validate and stage proposed tools
      - Manage Council vote workflow
      - Activate approved tools (registers + creates v1 version entry)
      - Wrap tool execution with analytics recording
    """

    def __init__(self, db: Session):
        """Init."""

        self.db = db
        self.factory = ToolFactory()
        self.versioning = ToolVersioningService(db)
        self.analytics = ToolAnalyticsService(db)

    # ──────────────────────────────────────────────────────────────
    # PROPOSE
    # ──────────────────────────────────────────────────────────────

    def propose_tool(self, request: ToolCreationRequest) -> Dict[str, Any]:
        """
        Agent proposes a new tool creation.
        Returns approval workflow status.
        """
        # Validate code
        validation = self.factory.validate_tool_code(request.code_template)
        if not validation["valid"]:
            return {"proposed": False, "error": validation["error"]}

        # Task agents (3xxxx) cannot create tools
        if request.created_by_agentium_id.startswith('3'):
            return {"proposed": False, "error": "Task agents cannot create tools"}

        # Check for name collision
        existing = self.db.query(ToolStaging).filter(
            ToolStaging.tool_name == request.tool_name
        ).first()
        if existing:
            return {
                "proposed": False,
                "error": f"Tool '{request.tool_name}' already exists (status: {existing.status}). "
                         "Use ToolVersioningService.propose_update() to update it.",
            }

        # Generate tool file (staged, not activated)
        tool_path = self.factory.generate_tool_file(request)

        # Determine if voting is required
        requires_vote = not request.created_by_agentium_id.startswith('0')

        # Create staging record
        staging_entry = ToolStaging(
            tool_name=request.tool_name,
            proposed_by_agentium_id=request.created_by_agentium_id,
            tool_path=str(tool_path),
            request_json=request.json(),
            requires_vote=requires_vote,
            status="pending_approval" if requires_vote else "approved",
        )
        self.db.add(staging_entry)
        self.db.commit()
        self.db.refresh(staging_entry)

        # If requires vote, create voting session
        if requires_vote:
            council = self.db.query(Agent).filter(
                Agent.agent_type == "council_member",
                Agent.status == "active"
            ).all()

            # FIX: removed the unused `from backend.services.persistent_council import persistent_council`
            # that was imported here but never actually called. If council notification is needed,
            # implement it explicitly via persistent_council.notify_council(...) here.

            voting = AmendmentVoting(
                constitution_id=None,
                proposed_by_agentium_id=request.created_by_agentium_id,
                proposed_changes=f"Tool Creation: {request.tool_name}",
                rationale=request.rationale,
                status=AmendmentStatus.PROPOSED,
                votes_required=len(council),
            )
            self.db.add(voting)
            self.db.commit()

            # Link voting id to staging
            staging_entry.voting_id = voting.id
            self.db.commit()

            return {
                "proposed": True,
                "tool_name": request.tool_name,
                "status": "pending_vote",
                "voting_id": voting.id,
                "requires_council_approval": True,
                "council_members": [c.agentium_id for c in council],
            }

        # Head of Council — auto-approve and activate
        activation = self.activate_tool(request.tool_name, staging_entry.id)
        return {
            "proposed": True,
            "tool_name": request.tool_name,
            "status": "activated",
            "activated": activation["success"],
            "error": activation.get("error"),
        }

    # ──────────────────────────────────────────────────────────────
    # VOTE
    # ──────────────────────────────────────────────────────────────

    def vote_on_tool(
        self, tool_name: str, voter_agentium_id: str, vote: str
    ) -> Dict[str, Any]:
        """Council member votes on tool creation proposal."""
        voting = self.db.query(AmendmentVoting).filter(
            AmendmentVoting.proposed_changes.like(f"%Tool Creation: {tool_name}%"),
            AmendmentVoting.status.in_([AmendmentStatus.PROPOSED, AmendmentStatus.VOTING]),
        ).first()

        if not voting:
            return {"voted": False, "error": "Voting session not found"}

        voting.cast_vote(vote, voter_agentium_id)
        self.db.commit()

        if voting.check_quorum():
            voting.finalize_voting()
            self.db.commit()

            if voting.status == AmendmentStatus.APPROVED:
                staging_entry = self.db.query(ToolStaging).filter(
                    ToolStaging.tool_name == tool_name
                ).first()

                if staging_entry:
                    activation = self.activate_tool(tool_name, staging_entry.id)
                    return {
                        "voted": True,
                        "tool_name": tool_name,
                        "voting_complete": True,
                        "approved": True,
                        "activated": activation["success"],
                    }

        return {
            "voted": True,
            "tool_name": tool_name,
            "voting_complete": False,
            "current_votes": {
                "for": voting.votes_for,
                "against": voting.votes_against,
                "abstain": voting.votes_abstain,
            },
        }

    # ──────────────────────────────────────────────────────────────
    # ACTIVATE
    # ──────────────────────────────────────────────────────────────

    def activate_tool(self, tool_name: str, staging_id: str) -> Dict[str, Any]:
        """
        Activate a staged tool:
        1. Run tests
        2. Load and register in tool_registry
        3. Create initial ToolVersion (v1) via ToolVersioningService
        4. Update staging status
        5. Audit log
        """
        staging_entry = self.db.query(ToolStaging).filter(
            ToolStaging.id == staging_id,
            ToolStaging.tool_name == tool_name,
        ).first()

        if not staging_entry:
            return {"success": False, "error": "Tool staging record not found"}

        request = ToolCreationRequest(**json.loads(staging_entry.request_json))

        # Run tests if provided
        test_result = None
        if request.test_cases:
            test_result = self.factory.run_tests(tool_name, request.test_cases)
            if not test_result["passed"]:
                return {
                    "success": False,
                    "error": "Tests failed",
                    "test_results": test_result,
                }

        # Load the tool module
        load_result = self.factory.load_tool(tool_name)
        if not load_result["loaded"]:
            return {"success": False, "error": load_result["error"]}

        # Register in tool registry
        tool_registry.register_tool(
            name=tool_name,
            description=request.description,
            function=load_result["tool_instance"].execute,
            parameters={
                p.name: {"type": p.type, "description": p.description}
                for p in request.parameters
            },
            authorized_tiers=request.authorized_tiers,
        )

        # Create initial version record (v1)
        tool_path = staging_entry.tool_path
        code = load_result["tool_instance"].__class__.__module__  # fallback
        try:
            from pathlib import Path
            code = Path(tool_path).read_text()
        except Exception:
            pass

        self.versioning.create_initial_version(
            tool_name=tool_name,
            code=code,
            tool_path=tool_path,
            authored_by=request.created_by_agentium_id,
            voting_id=staging_entry.voting_id,
        )

        # Update staging
        staging_entry.status = "activated"
        staging_entry.activated_at = datetime.utcnow()
        staging_entry.current_version = 1
        self.db.commit()

        self._log_tool_activation(request.created_by_agentium_id, tool_name)

        return {
            "success": True,
            "tool_name": tool_name,
            "authorized_tiers": request.authorized_tiers,
            "test_results": test_result,
            "version": "v1.0.0",
        }

    # ──────────────────────────────────────────────────────────────
    # EXECUTE (analytics-wrapped)
    # ──────────────────────────────────────────────────────────────

    def execute_tool(
        self,
        tool_name: str,
        called_by: str,
        kwargs: Dict[str, Any],
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a registered tool with automatic analytics recording.
        Use this instead of calling tool_registry directly when analytics is needed.

        NOTE: the ToolVersion lookup and the ToolUsageLog write each run on an
        INDEPENDENT session. The caller (e.g. AgentOrchestrator) may hand us a
        long-lived shared session that has already hit a failed transaction. If we
        queried/committed on that session here, every tool call would blow up with a
        SQLAlchemy "current transaction is aborted" rollback error — even for tools
        that never touch the DB (e.g. desktop_screen_size) or tools that open their
        own session (preference_*). Isolating these reads/writes keeps a poisoned
        caller session from contaminating tool execution.
        """
        # Resolve current version number on a throwaway session.
        from backend.models.entities.tool_version import ToolVersion
        try:
            with get_db_context() as vdb:
                active_version = (
                    vdb.query(ToolVersion)
                    .filter(ToolVersion.tool_name == tool_name, ToolVersion.is_active == True)
                    .first()
                )
        except Exception:
            active_version = None
        version_number = active_version.version_number if active_version else 1

        result = {}
        with self.analytics.record(
            tool_name=tool_name,
            called_by=called_by,
            task_id=task_id,
            tool_version=version_number,
            input_kwargs=kwargs,
        ) as ctx:
            tool_fn = tool_registry.get_tool_function(tool_name)
            if not tool_fn:
                ctx.set_error(f"Tool '{tool_name}' not found in registry")
                return {"status": "error", "error": f"Tool '{tool_name}' not found"}

            # Inject db + agent_id for tools whose signatures declare them
            # (e.g. deep_think_tool).  Uses inspect so every existing tool
            # is completely unaffected — they don't declare these params.
            import inspect as _inspect
            _sig = _inspect.signature(tool_fn)
            if "db" in _sig.parameters:
                kwargs["db"] = self.db
            if "agent_id" in _sig.parameters and "agent_id" not in kwargs:
                kwargs["agent_id"] = called_by

            # Async-aware dispatch — deep_think and any future async tools
            # return coroutines that must be run; all existing sync tools hit
            # the else-branch and behave exactly as before.
            import asyncio as _asyncio
            if _inspect.iscoroutinefunction(tool_fn):
                try:
                    _loop = _asyncio.get_running_loop()
                except RuntimeError:
                    _loop = None
                if _loop and _loop.is_running():
                    # Already inside an event loop (FastAPI request context):
                    # run the coroutine in a fresh thread so we don't deadlock.
                    import concurrent.futures as _cf
                    with _cf.ThreadPoolExecutor(max_workers=1) as _pool:
                        result = _pool.submit(
                            _asyncio.run, tool_fn(**kwargs)
                        ).result(timeout=120)
                else:
                    result = _asyncio.run(tool_fn(**kwargs))
            else:
                result = tool_fn(**kwargs)

            if isinstance(result, dict):
                ctx.set_output_size(len(str(result)))

        return result

    # ──────────────────────────────────────────────────────────────
    # SELF-IMPROVEMENT — composite tool from repeated patterns
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def create_from_pattern(pattern_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        Build and register a composite tool from a repeated tool-call sequence.

        `pattern_data` is expected to carry:
            sequence     : list[str] of tool names executed in order
            count        : how often the pattern was observed
            success_rate : observed success rate of the pattern

        The composite tool runs each named tool in sequence, threading the
        previous result into the next tool's kwargs. It is created by the
        Head (00001) so it auto-approves and activates without a Council
        vote — self-improvement should not require human/legislative sign-off
        for an optimization it has high confidence in.

        Returns the propose_tool() result, or an error dict if the pattern
        cannot be materialised.
        """
        from backend.core.tool_registry import tool_registry

        sequence = pattern_data.get("sequence") or []
        if not sequence:
            return {"created": False, "error": "empty sequence"}

        # Only chain tools that actually exist in the live registry.
        resolved = [t for t in sequence if tool_registry.get_tool_function(t)]
        if not resolved:
            return {"created": False, "error": "no registered tools in sequence"}

        tool_name = f"composite_{abs(hash('|'.join(resolved))) % (10 ** 8):08d}"

        # Build the execute() body: thread results through the sequence.
        # No leading indentation here — generate_tool_file indents every line
        # inside execute() via _indent_code. The import is inlined so the
        # generated module resolves tool_registry at load time.
        body = [
            "from backend.core.tool_registry import tool_registry",
            "result = kwargs",
            "",
        ]
        for name in resolved:
            body.append(f'_fn = tool_registry.get_tool_function("{name}")')
            body.append("if _fn is not None:")
            body.append(
                '    _inp = result if isinstance(result, dict) else {"input": result}'
            )
            body.append("    result = _fn(**_inp)")
        body.append('return {"status": "success", "result": result}')
        code_template = "\n".join(body)

        # Validate the generated body before it ever touches the registry.
        factory = ToolFactory()
        validation = factory.validate_tool_code(code_template)
        if not validation["valid"]:
            return {"created": False, "error": validation["error"]}

        request = ToolCreationRequest(
            tool_name=tool_name,
            description=(
                "Auto-composite tool from repeated sequence: "
                + ", ".join(resolved)
            ),
            parameters=[],
            code_template=code_template,
            test_cases=[],
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
            created_by_agentium_id="00001",
            rationale=(
                "Self-improvement: detected repeated tool sequence "
                f"(count={pattern_data.get('count')}, "
                f"success_rate={pattern_data.get('success_rate')})."
            ),
        )

        svc = ToolCreationService(db)
        outcome = svc.propose_tool(request)
        outcome["tool_name"] = tool_name
        outcome["created"] = outcome.get("proposed", False)
        return outcome

    # ──────────────────────────────────────────────────────────────

    def list_tools(
        self,
        status: Optional[str] = None,
        authorized_for_tier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List all tools with optional status and tier filters."""
        q = self.db.query(ToolStaging)
        if status:
            q = q.filter(ToolStaging.status == status)
        tools = q.all()

        result = [t.to_dict() for t in tools]

        if authorized_for_tier:
            filtered = []
            for t in result:
                # FIX: to_dict() may serialize request_json as a dict (already parsed)
                # or as a JSON string depending on the entity implementation.
                # Guard both cases to prevent TypeError on json.loads(dict).
                raw = t.get("request_json", {})
                if isinstance(raw, str):
                    try:
                        parsed = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        parsed = {}
                elif isinstance(raw, dict):
                    parsed = raw
                else:
                    parsed = {}

                if authorized_for_tier in parsed.get("authorized_tiers", []):
                    filtered.append(t)
            result = filtered

        return {"tools": result, "total": len(result)}

    # ──────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────

    def _log_tool_activation(self, agentium_id: str, tool_name: str):
        """Log tool activation."""

        audit = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.SYSTEM,
            actor_type='agent',
            actor_id=agentium_id,
            action="tool_activated",
            target_type='tool',
            target_id=tool_name,
            description=f"Tool '{tool_name}' activated and registered",
            after_state={
                "tool_name": tool_name,
                "activated_by": agentium_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        self.db.add(audit)
        self.db.commit()
"""
Agent Orchestrator - Central routing and governance coordinator.
Enforces hierarchy (0xxxx→1xxxx→2xxxx→3xxxx) and integrates Vector DB context.
 Tool execution, idle governance coordination, WebSocket broadcasting,
     metrics collection, and circuit breaker for failing agents.
"""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from backend.models.schemas.messages import AgentMessage, RouteResult
from backend.services.message_bus import MessageBus, get_message_bus, HierarchyValidator
from backend.core.vector_store import get_vector_store, VectorStore
from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.models.entities.task import TaskStatus, Task
from backend.core.tool_registry import tool_registry
from backend.services.idle_governance import idle_budget, token_optimizer
from backend.api.routes.websocket import manager
from backend.core.constitutional_guard import ConstitutionalGuard, Verdict, ViolationSeverity
from backend.services.tool_creation_service import ToolCreationService
from backend.services.critic_agents import critic_service, CriticType
from backend.services.api_manager import api_manager
from backend.services.model_provider import ModelService
from backend.models.schemas.tool_creation import ToolCreationRequest

# NEW: Tool execution imports
from backend.services.host_access import HostAccessService
from backend.services.clarification_service import ClarificationService
from backend.tools.browser_router import should_use_stealth_browser_with_runtime, register_stealth_domain
from backend.services.prompt_template_manager import prompt_template_manager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Circuit Breaker States
# ---------------------------------------------------------------------------

CB_CLOSED = "closed"          # Normal operation
CB_OPEN = "open"              # Blocking requests – agent is failing
CB_HALF_OPEN = "half_open"    # Allowing one probe to test recovery

CB_FAILURE_THRESHOLD = 5      # Consecutive failures before opening
CB_RECOVERY_SECONDS = 60      # Seconds before half-open probe


class AgentOrchestrator:
    """
    Central orchestrator for Agentium multi-agent governance.
    Handles intent processing, routing decisions, context enrichment, and TOOL EXECUTION.
    Includes per-agent circuit breaker and routing metrics collection.
    """

    def __init__(self, db: Session, message_bus: Optional[MessageBus] = None):
        self.db = db
        self.message_bus = message_bus
        self.vector_store: Optional[VectorStore] = None
        self._routing_cache: Dict[str, datetime] = {}
        self.host_access = HostAccessService("00001")  # For system-level operations
        self.guard = ConstitutionalGuard(db)  # NEW: Constitutional Guard

        # --- Metrics ---
        self._metrics: Dict[str, Any] = {
            "total_routed": 0,
            "total_errors": 0,
            "latency_samples": [],          # Last N latency values (ms)
            "per_agent_volume": defaultdict(int),
            "per_tier_volume": defaultdict(int),
            "error_counts": defaultdict(int),
            "started_at": datetime.utcnow().isoformat(),
        }
        self._max_latency_samples = 500  # Rolling window size

        # --- Circuit Breakers (per agent) ---
        # { agent_id: {"state": CB_*, "failures": int, "opened_at": float|None} }
        self._circuit_breakers: Dict[str, Dict[str, Any]] = {}

    async def execute_task(self, task: Task, agent: Agent, db: Session):
        # Allocate optimal model for this task
        config_id = await token_optimizer.allocate_model_for_agent(agent, task, db)

        # Update agent with allocated model
        agent.preferred_config_id = config_id

        # Get the model info — refresh then eagerly load the relationship
        # to avoid a lazy-load / DetachedInstanceError after the session refresh.
        db.refresh(agent)
        db.refresh(agent, attribute_names=["preferred_config"])
        if agent.preferred_config is None:
            raise ValueError(
                f"Agent {agent.agentium_id} has preferred_config_id={config_id!r} "
                "but the related ModelConfig row was not found."
            )
        model_key = f"{agent.preferred_config.provider}:{agent.preferred_config.default_model}"
        model = api_manager.models.get(model_key)

        # Build a provider- and task-aware system prompt using the agent's ethos.
        # agent_tier is derived from the ID prefix: 0xxxx→0, 1xxxx→1, 2xxxx→2, 3xxxx→3.
        agent_tier = int(agent.agentium_id[0]) if agent.agentium_id[0].isdigit() else 3
        system_prompt, max_tokens_multiplier, requires_cot = (
            prompt_template_manager.build_system_prompt(
                provider=agent.preferred_config.provider,
                model_name=agent.preferred_config.default_model,
                task_description=task.description,
                agent_ethos=agent.ethos,
                agent_tier=agent_tier,
            )
        )

        # Execute with allocated model and the template-built system prompt.
        result = await ModelService.generate_with_agent(
            agent=agent,
            user_message=task.description,
            config_id=config_id,
            system_prompt_override=system_prompt,
            max_tokens_multiplier=max_tokens_multiplier,
            chain_of_thought=requires_cot,
        )

        # Record usage
        token_optimizer.update_token_count(
            agent_id=agent.agentium_id,
            tokens_used=result.get("tokens_used", 0)
        )

        # Workflow §3: Compress ethos after sub-step execution to prevent
        # cognitive bloat.  Completed steps are pruned from progress markers.
        completed_steps = result.get("completed_steps", [])
        agent.compress_ethos(db, completed_steps=completed_steps)

        return result

    async def initialize(self):
        """Initialize orchestrator dependencies."""
        if self.message_bus is None:
            self.message_bus = await get_message_bus()
        self.vector_store = get_vector_store()
        await self.guard.initialize()  # NEW: Initialize guard

    async def process_intent(self, raw_input: str, source_id: str, target_id: Optional[str] = None) -> RouteResult:
        """
        Process intent and route to appropriate agent.
        Includes tool detection, metrics recording, and circuit breaker checks.
        """
        start = datetime.utcnow()
        start_mono = time.monotonic()

        # CRITICAL: Wake from idle on any user activity
        token_optimizer.record_activity()

        # Validate source
        source = self._get_agent(source_id)
        if not source:
            self._record_metric(source_id, success=False)
            return RouteResult(success=False, message_id="", error=f"Agent {source_id} not found")

        # --- Circuit breaker check ---
        recipient = target_id or self._get_parent_id(source_id)
        cb_result = self._check_circuit_breaker(recipient)
        if cb_result is not None:
            self._record_metric(source_id, success=False)
            return cb_result

        # --- Constitutional Guard Check ---
        # We treat raw inputs as "intent" actions for now.
        # Future: deeper inspection of tool arguments if applicable.
        decision = await self.guard.check_action(
            agent_id=source_id,
            action="process_intent",
            context={"raw_input": raw_input, "target_id": target_id}
        )

        if decision.verdict == Verdict.BLOCK:
            await self._log(
                source_id,
                "constitutional_violation",
                f"Blocked action: {decision.explanation}",
                AuditLevel.CRITICAL
            )
            self._record_metric(source_id, success=False)
            return RouteResult(
                success=False,
                message_id="",
                error=f"Constitutional Violation: {decision.explanation}"
            )

        elif decision.verdict == Verdict.VOTE_REQUIRED:
            # For now, we block but indicate a vote is needed.
            # In Phase 6, we will auto-trigger the VotingService here.
            await self._log(
                source_id,
                "constitutional_vote_required",
                f"Vote required: {decision.explanation}",
                AuditLevel.WARNING
            )
            return RouteResult(
                success=False,
                message_id="",
                error=f"Action requires Council Vote: {decision.explanation}"
            )

        # Check if message is a tool execution command
        tool_detection = self._detect_tool_intent(raw_input, source_id)
        if tool_detection["is_tool_command"]:
            return await self._execute_tool_directly(tool_detection, source_id, start)

        # Check if message is a tool creation request (meta-tool)
        if self._detect_tool_creation_intent(raw_input, source_id):
            return await self._handle_tool_creation_request(raw_input, source_id, start)

        # Determine target
        direction = self._get_direction(source_id, recipient)

        # Create message
        msg = AgentMessage(
            sender_id=source_id,
            recipient_id=recipient,
            content=raw_input,
            message_type="intent",
            route_direction=direction
        )

        # Validate hierarchy
        if not HierarchyValidator.can_route(source_id, recipient, direction):
            await self._log(source_id, "routing_violation", f"Attempted {direction} to {recipient}", AuditLevel.WARNING)
            self._record_metric(source_id, success=False)
            return RouteResult(success=False, message_id=msg.message_id, error="Hierarchy violation")

        # Enrich and route
        msg = await self.enrich_with_context(msg)

        # Execute based on direction with tool enrichment
        if direction == "up":
            result = await self._route_up_with_tools(msg)
        elif direction == "down":
            result = await self._route_down_with_tools(msg)
        else:
            result = await self.message_bus.publish(msg)

        latency_ms = (time.monotonic() - start_mono) * 1000
        result.latency_ms = latency_ms

        # --- Record metrics & circuit breaker feedback ---
        self._record_metric(source_id, success=result.success, latency_ms=latency_ms)
        self._update_circuit_breaker(recipient, success=result.success)

        # Broadcast via WebSocket to frontend
        await self._broadcast_orchestration_event(msg, result)

        return result

    # NEW: Tool Detection Method
    def _detect_tool_intent(self, content: str, agent_id: str) -> Dict[str, Any]:
        """
        Detect if user message is requesting tool execution.
        Examples: "navigate to google.com", "read file /tmp/data.txt"
        """
        tool_commands = {
            "navigate": "browser_control",
            "browse": "browser_control",
            "read file": "read_file",
            "write file": "write_file",
            "execute": "execute_command",
            "run command": "execute_command"
        }

        content_lower = content.lower()
        for command_phrase, tool_name in tool_commands.items():
            if command_phrase in content_lower:
                # Check if agent is authorized for this tool
                agent_tier = self._get_tier(agent_id)

                # For browser commands, use router to pick stealth vs standard
                if tool_name == "browser_control":
                    import re
                    url_match = re.search(r'https?://[^\s]+', content)
                    url = url_match.group(0) if url_match else ""
                    choice = should_use_stealth_browser_with_runtime(url)
                    tool_name = choice.tool_name  # nodriver_navigate or desktop_browse_to
                    logger.debug(
                        "_detect_tool_intent: browser route for %r → %s (%s)",
                        url, tool_name, choice.reason
                    )

                tool = tool_registry.get_tool(tool_name)

                if tool and agent_tier in tool.get("authorized_tiers", []):
                    # Extract parameters from natural language
                    params = self._extract_parameters_from_text(content, tool["parameters"])
                    return {
                        "is_tool_command": True,
                        "tool_name": tool_name,
                        "parameters": params
                    }

        return {"is_tool_command": False}

    # NEW: Tool Creation Detection
    def _detect_tool_creation_intent(self, content: str, agent_id: str) -> bool:
        """Detect if agent wants to create a new tool."""
        creation_phrases = [
            "create a tool",
            "build a tool for",
            "make a function to",
            "add capability to"
        ]

        return any(phrase in content.lower() for phrase in creation_phrases) and agent_id.startswith(('0', '1', '2'))

    # NEW: Tool Execution Method
    async def _execute_tool_directly(self, tool_detection: Dict, agent_id: str, start_time: datetime) -> RouteResult:
        """
        Execute tool directly without hierarchical routing.
        Routes through ToolCreationService.execute_tool() so every call is
        recorded in ToolUsageLog (analytics, latency, error tracking).
        """
        tool_name = tool_detection["tool_name"]
        params = tool_detection["parameters"]

        # Phase 6.1: use analytics-wrapped executor instead of bare tool_registry call.
        # This records latency, success/failure, caller identity, and task context
        # automatically via ToolAnalyticsService inside execute_tool().
        tool_svc = ToolCreationService(self.db)
        result = tool_svc.execute_tool(
            tool_name=tool_name,
            called_by=agent_id,
            kwargs=params,
            task_id=tool_detection.get("task_id"),  # pass along if present
        )

        # If a standard browser call bounced with a bot-detection error, register
        # the domain as stealth-required so future calls route to nodriver automatically.
        if (
            tool_name == "desktop_browse_to"
            and result.get("status") == "error"
            and any(kw in str(result.get("error", "")).lower()
                    for kw in ("403", "captcha", "challenge", "blocked", "bot"))
        ):
            url = params.get("url", "")
            if url:
                from urllib.parse import urlparse
                hostname = urlparse(url).hostname or ""
                if hostname:
                    register_stealth_domain(hostname)
                    logger.warning(
                        "_execute_tool_directly: bot-detection on %s — "
                        "registered as stealth domain, retrying with nodriver",
                        hostname
                    )
                    # Retry immediately with stealth browser
                    result = tool_svc.execute_tool(
                        tool_name="nodriver_navigate",
                        called_by=agent_id,
                        kwargs=params,
                        task_id=tool_detection.get("task_id"),
                    )
                    tool_name = "nodriver_navigate"  # update for audit log

        # Log execution to audit trail (separate from analytics — audit is governance)
        await self._log(
            actor=agent_id,
            action="tool_execution",
            desc=f"Executed {tool_name} with params {params}",
            level=AuditLevel.INFO if result.get("status") == "success" else AuditLevel.ERROR
        )

        # Create result message
        msg_id = f"tool_{tool_name}_{datetime.utcnow().timestamp()}"

        return RouteResult(
            success=result.get("status") == "success",
            message_id=msg_id,
            routed_to="tool_executor",
            constitutional_basis=[f"Tool execution by {agent_id}"],
            metadata={
                "tool_name": tool_name,
                "parameters": params,
                "tool_result": result
            },
            latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
        )

    # FIXED: Tool Creation Handler
    async def _handle_tool_creation_request(self, content: str, agent_id: str, start_time: datetime) -> RouteResult:
        """
        Process request to create a new tool.

        Tier rules (mirrors ToolCreationService.propose_tool):
          - Head (0xxxx)   → auto-approves, activates immediately
          - Council/Lead (1xxxx/2xxxx) → proposal staged, Council vote triggered
          - Task (3xxxx)   → blocked, escalated to parent Lead

        FIX: Previously this method always fell through to escalate_to_council()
        for Head/Council/Lead agents due to a misplaced return and TODO comment,
        making natural-language tool creation non-functional for all tiers.

        Now: Task agents still escalate. Head/Council/Lead agents get a minimal
        ToolCreationRequest parsed from the natural language content and sent
        directly to ToolCreationService.propose_tool(). The service handles
        tier-based approval internally (Head auto-activates, others go to vote).

        Note: natural language parsing here produces a minimal/stub request.
        Agents should use the structured POST /tool-management/propose endpoint
        for production tool proposals with full code templates and test cases.
        """
        # Task agents cannot create tools — escalate to their Lead instead
        if agent_id.startswith("3"):
            return await self.escalate_to_council(
                issue=f"Tool creation request from task agent {agent_id}: {content}",
                reporter_id=agent_id
            )

        # Parse a minimal ToolCreationRequest from natural language.
        # This extracts a best-effort tool name from the content so the proposal
        # can enter the proper workflow (vote or auto-activate).
        # Agents wanting full control (code template, parameters, test cases)
        # should call POST /tool-management/propose directly.
        import re
        tool_name_match = re.search(
            r'(?:create a tool|build a tool for|make a function to|add capability to)\s+["\']?([a-zA-Z0-9_\- ]+)["\']?',
            content,
            re.IGNORECASE,
        )
        # Sanitize to snake_case identifier
        raw_name = tool_name_match.group(1).strip() if tool_name_match else "unnamed_tool"
        tool_name = re.sub(r'[^a-z0-9]+', '_', raw_name.lower()).strip('_') or "unnamed_tool"

        try:
            request = ToolCreationRequest(
                tool_name=tool_name,
                description=f"Agent-initiated tool proposal: {content[:200]}",
                code_template="# Stub — replace with real implementation",
                parameters=[],
                authorized_tiers=[],
                rationale=content,
                created_by_agentium_id=agent_id,
            )
        except Exception as exc:
            # Pydantic validation failure — fall back to escalation so the
            # request is not silently dropped.
            logger.warning(
                "_handle_tool_creation_request: could not build ToolCreationRequest for %s: %s",
                agent_id, exc
            )
            return await self.escalate_to_council(
                issue=f"Tool creation request (parse failed) from {agent_id}: {content}",
                reporter_id=agent_id,
            )

        tool_svc = ToolCreationService(self.db)
        result = tool_svc.propose_tool(request)

        await self._log(
            actor=agent_id,
            action="tool_creation_proposed",
            desc=f"Natural-language tool proposal '{tool_name}' by {agent_id}: proposed={result.get('proposed')}",
            level=AuditLevel.INFO if result.get("proposed") else AuditLevel.WARNING,
        )

        msg_id = f"tool_propose_{tool_name}_{datetime.utcnow().timestamp()}"
        return RouteResult(
            success=result.get("proposed", False),
            message_id=msg_id,
            routed_to="tool_creation_service",
            constitutional_basis=[f"Tool creation by {agent_id}"],
            metadata=result,
            latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
            error=result.get("error") if not result.get("proposed") else None,
        )

    # NEW: Enhanced routing with tool ability checks
    async def _route_up_with_tools(self, msg: AgentMessage) -> RouteResult:
        """Route up with context about what tools parent can execute."""
        parent = self._get_agent(msg.recipient_id)
        if parent:
            # Add parent's available tools to context
            parent_tier = self._get_tier(parent.agentium_id)
            available_tools = tool_registry.list_tools(parent_tier)
            msg.rag_context = msg.rag_context or {}
            msg.rag_context["available_tools"] = list(available_tools.keys())

        return await self.message_bus.route_up(msg)

    async def _route_down_with_tools(self, msg: AgentMessage) -> RouteResult:
        """Route down with tool assignments for task execution."""
        # If task requires tools, assign them
        if hasattr(msg, 'payload') and msg.payload and "required_tools" in msg.payload:
            required_tools = msg.payload["required_tools"]

            # Verify recipient has access to required tools
            recipient_tier = self._get_tier(msg.recipient_id)
            available_tools = tool_registry.list_tools(recipient_tier)

            unauthorized_tools = [t for t in required_tools if t not in available_tools]
            if unauthorized_tools:
                # Escalate to parent if tools aren't available
                msg.content += f"\n[ESCALATION] Required tools unavailable: {unauthorized_tools}"
                return await self.message_bus.route_up(msg)

        return await self.message_bus.route_down(msg)

    # ENHANCED: Idle governance integration
    async def escalate_to_council(self, issue: str, reporter_id: str) -> RouteResult:
        """Escalate issue to Council tier (1xxxx)."""
        # Wake from idle
        token_optimizer.record_activity()

        msg = AgentMessage(
            sender_id=reporter_id,
            recipient_id="",
            message_type="escalation",
            content=issue,
            priority="high"
        )

        # Enrich with constitution
        if self.vector_store:
            articles = self.vector_store.query_constitution(issue, n_results=3)
            msg.constitutional_basis = articles.get("documents", [[]])[0]

        # NEW: Add tools needed for resolution
        resolution_tools = self._suggest_tools_for_issue(issue)
        msg.rag_context = {
            "resolution_tools": resolution_tools,
            "escalation_timestamp": datetime.utcnow().isoformat()
        }

        return await self.message_bus.route_up(msg, auto_find_parent=True)

    async def clarify_agent_confusion(
        self,
        agent: Agent,
        question: str,
        context: str = "",
        escalate: bool = False,
    ) -> Dict[str, Any]:
        """
        Called when a reincarnated or confused agent needs guidance about its
        inherited state.  Delegates to ClarificationService and, if the immediate
        supervisor cannot help, escalates up the hierarchy chain.

        Args:
            agent:     The confused agent requesting clarification.
            question:  The specific question the agent is asking.
            context:   Additional context about what confused the agent.
            escalate:  If True, walk the full hierarchy instead of asking only
                       the immediate supervisor.

        Returns:
            ClarificationService response dict (see ClarificationService docs).
        """
        token_optimizer.record_activity()

        if escalate:
            result = ClarificationService.escalate_clarification(
                agent=agent,
                question=question,
                db=self.db,
            )
        else:
            result = ClarificationService.consult_supervisor(
                agent=agent,
                db=self.db,
                question=question,
                context=context,
            )

        await self._log(
            actor=agent.agentium_id,
            action="clarification_requested",
            desc=f"Agent {agent.agentium_id} requested clarification: {question[:120]}",
        )

        return result


    def _suggest_tools_for_issue(self, issue: str) -> List[str]:
        """Suggest tools that might help resolve the issue."""
        suggestions = []

        if "file" in issue.lower():
            suggestions.append("read_file")
        if "browser" in issue.lower() or "web" in issue.lower():
            # Prefer stealth browser for web tasks since we don't have a URL yet
            suggestions.append("nodriver_navigate")
            suggestions.append("browser_control")
        if "command" in issue.lower() or "execute" in issue.lower():
            suggestions.append("execute_command")
        if "docker" in issue.lower() or "container" in issue.lower():
            suggestions.append("list_containers")

        return suggestions

    # ENHANCED: With tool checking + critic review (Phase 6.2)
    async def delegate_to_task(
        self,
        task: Dict,
        lead_id: str,
        task_id: Optional[str] = None,
        retry_count: int = 0,
    ) -> RouteResult:
        """Delegate from Lead (2xxxx) to Task (3xxxx).

        After execution, routes output through the appropriate critic before
        returning the result up the hierarchy.
          PASS     → return result normally
          REJECT   → retry within same team (no Council escalation)
          ESCALATE → forward to Council once max_retries exhausted
        """
        # Wake from idle
        token_optimizer.record_activity()

        if not task_id:
            task_id = await self._find_available_task(lead_id)

        if not task_id:
            return RouteResult(success=False, message_id="", error="No Task Agent available")

        msg = AgentMessage(
            sender_id=lead_id,
            recipient_id=task_id,
            message_type="delegation",
            content=task.get("description", ""),
            payload=task,
            route_direction="down"
        )

        # Enrich with task-specific tool patterns
        if self.vector_store:
            patterns = self.vector_store.get_collection("task_patterns").query(
                query_texts=[task.get("description", "")],
                n_results=3
            )
            msg.rag_context = {"patterns": patterns}

        result = await self.message_bus.route_down(msg)

        await self._log(
            actor=lead_id,
            action="task_delegation",
            desc=f"Assigned task to {task_id} with tools: {task.get('allowed_tools', 'default')}",
            target=task_id
        )

        # ── Phase 6.2: Critic Review ──────────────────────────────────────
        # Only review when execution produced real output content.
        output_content = ""
        if result.success and result.metadata:
            output_content = (
                result.metadata.get("output")
                or result.metadata.get("result")
                or ""
            )

        if result.success and output_content:
            critic_type = self._resolve_critic_type(task)
            db_task_id = task.get("id") or task_id

            review = await critic_service.review_task_output(
                db=self.db,
                task_id=db_task_id,
                output_content=output_content,
                critic_type=critic_type,
                subtask_id=task_id,
                retry_count=retry_count,
            )

            verdict = review.get("verdict")

            await self._log(
                actor=lead_id,
                action=f"critic_review_{verdict}",
                desc=(
                    f"Critic ({critic_type.value}) verdict for task {db_task_id}: {verdict}"
                    + (f" — {review.get('rejection_reason', '')[:150]}" if verdict != "pass" else "")
                ),
                level=AuditLevel.INFO if verdict == "pass" else AuditLevel.WARNING,
                target=task_id,
            )

            if verdict == "reject":
                # Retry within same team — no Council replanning
                logger.warning(
                    "Critic REJECTED output for task %s (attempt %d/%d). Retrying within team...",
                    db_task_id, retry_count + 1, review.get("max_retries", 5),
                )
                return await self.delegate_to_task(
                    task=task,
                    lead_id=lead_id,
                    task_id=None,          # Re-pick — allow load balancer to choose
                    retry_count=retry_count + 1,
                )

            elif verdict == "escalate":
                # Max retries exhausted — escalate to Council for replanning
                logger.error(
                    "Critic ESCALATING task %s to Council after %d failed retries.",
                    db_task_id, retry_count,
                )
                return await self.escalate_to_council(
                    issue=(
                        f"Task {db_task_id} failed critic review after {retry_count} retries. "
                        f"Critic type: {critic_type.value}. "
                        f"Reason: {review.get('rejection_reason', 'unknown')}"
                    ),
                    reporter_id=lead_id,
                )

            # verdict == "pass" — fall through and return result normally

        return result

    def _resolve_critic_type(self, task: Dict) -> CriticType:
        """
        Map task type/hints to the appropriate CriticType.

        Precedence:
          1. Explicit 'critic_type' key on the task dict
          2. task_type field heuristics (code → CodeCritic, plan → PlanCritic)
          3. Default: OutputCritic
        """
        explicit = task.get("critic_type", "").lower()
        if explicit in ("code", "output", "plan"):
            return CriticType(explicit)

        task_type = str(task.get("task_type") or task.get("type") or "").lower()
        if any(kw in task_type for kw in ("code", "script", "function", "sql")):
            return CriticType.CODE
        if any(kw in task_type for kw in ("plan", "dag", "strategy", "decompose")):
            return CriticType.PLAN

        return CriticType.OUTPUT

    # ENHANCED: With constitution reading
    async def enrich_with_context(self, msg: AgentMessage) -> AgentMessage:
        """Inject Vector DB context before routing."""
        if not self.vector_store:
            return msg

        agent_type = self._get_type(msg.sender_id)
        ctx = self.vector_store.query_hierarchical_context(
            agent_type=agent_type,
            task_description=msg.content,
            n_results=5
        )

        const = self.vector_store.query_constitution(msg.content, n_results=2)

        # NEW: Also query tool usage patterns
        tool_ctx = self.vector_store.get_collection("tool_usage").query(
            query_texts=[msg.content],
            n_results=3
        ) if self.vector_store.has_collection("tool_usage") else None

        msg.rag_context = {
            "hierarchy": ctx,
            "constitution": const,
            "tool_patterns": tool_ctx,
            "timestamp": datetime.utcnow().isoformat()
        }
        return msg

    # NEW: WebSocket broadcasting for real-time updates
    async def _broadcast_orchestration_event(self, msg: AgentMessage, result: RouteResult):
        """Broadcast orchestration events to connected clients."""
        event_data = {
            "event_type": "orchestration",
            "timestamp": datetime.utcnow().isoformat(),
            "message": {
                "message_id": msg.message_id,
                "sender": msg.sender_id,
                "recipient": msg.recipient_id,
                "type": msg.message_type,
                "direction": msg.route_direction
            },
            "result": {
                "success": result.success,
                "routed_to": result.routed_to,
                "latency_ms": result.latency_ms
            },
            "idle_status": token_optimizer.get_status()  # Include idle state
        }

        await manager.broadcast(event_data)

    # Parameter extraction from natural language
    def _extract_parameters_from_text(self, text: str, tool_params: Dict) -> Dict[str, Any]:
        """Extract parameters from natural language using regex and simple parsing."""
        params = {}

        # URL extraction
        if "url" in tool_params and "http" in text:
            import re
            url_match = re.search(r'https?://[^\s]+', text)
            if url_match:
                params["url"] = url_match.group(0)

        # File path extraction
        if "filepath" in tool_params and ("/" in text or "\\" in text):
            import re
            path_match = re.search(r'(/[^\s]+|C:\\[^\s]+)', text)
            if path_match:
                params["filepath"] = path_match.group(0)

        # Default values
        for param_name, param_meta in tool_params.items():
            if param_name not in params and param_meta.get("default"):
                params[param_name] = param_meta["default"]

        return params

    # ------------------------------------------------------------------
    # Metrics Collection
    # ------------------------------------------------------------------

    def _record_metric(
        self,
        agent_id: str,
        success: bool,
        latency_ms: float = 0.0,
    ):
        """Record a routing operation metric."""
        self._metrics["total_routed"] += 1
        self._metrics["per_agent_volume"][agent_id] += 1

        tier = agent_id[0] if agent_id else "?"
        self._metrics["per_tier_volume"][tier] += 1

        if not success:
            self._metrics["total_errors"] += 1
            self._metrics["error_counts"][agent_id] += 1

        if latency_ms > 0:
            samples = self._metrics["latency_samples"]
            samples.append(latency_ms)
            if len(samples) > self._max_latency_samples:
                self._metrics["latency_samples"] = samples[-self._max_latency_samples:]

    def get_metrics(self) -> Dict[str, Any]:
        """Return a snapshot of routing metrics."""
        samples = self._metrics["latency_samples"]
        avg_latency = sum(samples) / len(samples) if samples else 0.0
        p95_latency = sorted(samples)[int(len(samples) * 0.95)] if len(samples) >= 20 else avg_latency

        return {
            "total_routed": self._metrics["total_routed"],
            "total_errors": self._metrics["total_errors"],
            "error_rate": (
                self._metrics["total_errors"] / self._metrics["total_routed"]
                if self._metrics["total_routed"] > 0 else 0.0
            ),
            "avg_latency_ms": round(avg_latency, 2),
            "p95_latency_ms": round(p95_latency, 2),
            "per_tier_volume": dict(self._metrics["per_tier_volume"]),
            "per_agent_volume": dict(self._metrics["per_agent_volume"]),
            "error_counts": dict(self._metrics["error_counts"]),
            "circuit_breakers": {
                aid: cb["state"] for aid, cb in self._circuit_breakers.items()
                if cb["state"] != CB_CLOSED
            },
            "started_at": self._metrics["started_at"],
        }

    # ------------------------------------------------------------------
    # Circuit Breaker
    # ------------------------------------------------------------------

    def _get_or_create_cb(self, agent_id: str) -> Dict[str, Any]:
        """Get or initialise circuit breaker state for an agent."""
        if agent_id not in self._circuit_breakers:
            self._circuit_breakers[agent_id] = {
                "state": CB_CLOSED,
                "failures": 0,
                "opened_at": None,
            }
        return self._circuit_breakers[agent_id]

    def _check_circuit_breaker(self, agent_id: str) -> Optional[RouteResult]:
        """
        Check circuit breaker before routing to an agent.

        Returns None if routing is allowed, or a RouteResult if blocked.
        """
        cb = self._get_or_create_cb(agent_id)

        if cb["state"] == CB_CLOSED:
            return None  # OK

        if cb["state"] == CB_OPEN:
            # Check if recovery window has elapsed
            if cb["opened_at"] and (time.monotonic() - cb["opened_at"]) >= CB_RECOVERY_SECONDS:
                cb["state"] = CB_HALF_OPEN
                logger.info("Circuit breaker for %s transitioning to HALF_OPEN", agent_id)
                return None  # Allow one probe
            # Still open – block
            return RouteResult(
                success=False,
                message_id="",
                error=(
                    f"Circuit breaker OPEN for agent {agent_id}. "
                    f"Agent has failed {cb['failures']} consecutive operations. "
                    f"Retry after {CB_RECOVERY_SECONDS}s recovery window."
                ),
            )

        # HALF_OPEN – allow the probe through
        return None

    def _update_circuit_breaker(self, agent_id: str, success: bool):
        """Update circuit breaker state after a routing result."""
        cb = self._get_or_create_cb(agent_id)

        if success:
            if cb["state"] in (CB_HALF_OPEN, CB_OPEN):
                logger.info("Circuit breaker for %s RESET to CLOSED", agent_id)
            cb["state"] = CB_CLOSED
            cb["failures"] = 0
            cb["opened_at"] = None
        else:
            cb["failures"] += 1
            if cb["state"] == CB_HALF_OPEN:
                # Probe failed → reopen
                cb["state"] = CB_OPEN
                cb["opened_at"] = time.monotonic()
                logger.warning("Circuit breaker for %s re-OPENED after failed probe", agent_id)
            elif cb["failures"] >= CB_FAILURE_THRESHOLD:
                cb["state"] = CB_OPEN
                cb["opened_at"] = time.monotonic()
                logger.warning(
                    "Circuit breaker OPENED for %s after %d failures",
                    agent_id, cb["failures"],
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def check_permission(self, from_id: str, to_id: str) -> bool:
        """Validate routing permission."""
        return HierarchyValidator.can_route(from_id, to_id, self._get_direction(from_id, to_id))

    def _get_agent(self, agent_id: str) -> Optional[Agent]:
        """Query agent from DB (cacheable in production)."""
        return self.db.query(Agent).filter_by(agentium_id=agent_id, is_active=True).first()

    def _get_parent_id(self, agent_id: str) -> str:
        """Get parent agent ID from DB."""
        agent = self._get_agent(agent_id)
        if agent and agent.parent:
            return agent.parent.agentium_id
        # Return generic tier target if no specific parent
        tier = HierarchyValidator.get_tier(agent_id)
        parents = {3: "2xxxx", 2: "1xxxx", 1: "00001"}
        return parents.get(tier, "00001")

    def _get_direction(self, from_id: str, to_id: str) -> str:
        """Determine routing direction."""
        from_tier = HierarchyValidator.get_tier(from_id)
        to_tier = HierarchyValidator.get_tier(to_id)

        if to_id == "broadcast":
            return "broadcast"
        if to_tier < from_tier:
            return "up"
        if to_tier > from_tier:
            return "down"
        return "lateral"

    def _get_tier(self, agent_id: str) -> str:
        """
        FIX: This method was called in three places (_detect_tool_intent,
        _route_up_with_tools, _route_down_with_tools) but was never defined
        on the class — every call would raise AttributeError at runtime.

        Returns the tier string for an agent ID by delegating to
        HierarchyValidator.get_tier(), which maps the ID prefix to a tier
        number and then maps that back to the string prefix used for
        tool registry authorization checks (e.g. "0", "1", "2", "3").
        """
        tier_num = HierarchyValidator.get_tier(agent_id)
        # HierarchyValidator.get_tier() returns an int (0-3).
        # The tool registry authorized_tiers uses the string prefix character.
        return str(tier_num)

    def _get_type(self, agent_id: str) -> str:
        """Map ID prefix to agent type string."""
        return {'0': 'head', '1': 'council', '2': 'lead', '3': 'task'}.get(agent_id[0], 'task')

    async def _find_available_task(self, lead_id: str) -> Optional[str]:
        """Find available Task Agent under Lead."""
        lead = self._get_agent(lead_id)
        if not lead:
            return None

        # NEW: Only return idle-enabled task agents if system is in idle mode
        if token_optimizer.idle_mode_active:
            for sub in lead.subordinates:
                if (sub.agent_type == AgentType.TASK_AGENT and
                    sub.status.value == 'active' and
                    sub.idle_mode_enabled):
                    return sub.agentium_id

        # Normal mode: any active task agent
        for sub in lead.subordinates:
            if sub.agent_type == AgentType.TASK_AGENT and sub.status.value == 'active':
                return sub.agentium_id

        return None

    async def _log(self, actor: str, action: str, desc: str, level=AuditLevel.INFO, target=None):
        """Write to audit log."""
        audit = AuditLog(
            level=level,
            category=AuditCategory.GOVERNANCE,
            actor_type="agent",
            actor_id=actor,
            action=action,
            description=desc,
            agentium_id=f"L{datetime.utcnow().strftime('%H%M%S')}",
            target_type="agent",
            target_id=target or "",
        )
        self.db.add(audit)
        self.db.commit()
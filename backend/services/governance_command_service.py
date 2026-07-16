"""
Governance Command Service.

A deterministic parser + executor for provisioning directives such as
"spawn a task agent", "spawn a lead agent", and "create a task".

Directives are detected from a natural-language message and executed through
the canonical service layer (ReincarnationService) according to the ISSUING
AGENT's authority (checked via the CapabilityRegistry). Authority gating is
performed both here (fast-fail with a clear PermissionError) and again inside
the reincarnation service (defence-in-depth).
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.models.entities.agents import (
    Agent,
    AgentType,
    AgentStatus,
    HeadOfCouncil,
    CouncilMember,
    LeadAgent,
    TaskAgent,
)
from backend.models.entities.task import Task, TaskType, TaskPriority
from backend.services.capability_registry import Capability, CapabilityRegistry
from backend.services.reincarnation_service import reincarnation_service

logger = logging.getLogger(__name__)


@dataclass
class GovernanceCommand:
    """A parsed provisioning directive."""

    kind: str  # "spawn_task_agent" | "spawn_lead_agent" | "create_task"
    name: Optional[str] = None
    description: Optional[str] = None
    capabilities: Optional[List[str]] = None


class GovernanceCommandService:
    """Deterministic detector + executor for provisioning directives."""

    TASK_PHRASES = [
        "spawn a task agent",
        "spawn task agent",
        "create a task agent",
        "create task agent",
        "provision a task agent",
    ]
    LEAD_PHRASES = [
        "spawn a lead agent",
        "spawn lead agent",
        "create a lead agent",
        "create lead agent",
        "provision a lead agent",
    ]
    CREATE_TASK_PHRASES = [
        "create a task",
        "create task",
        "new task",
        "add a task",
    ]

    _NAME_RE = re.compile(r"(?:named|called)\s+([A-Za-z0-9 _\-]{1,40})")

    # ──────────────────────────────────────────────────────────────────
    # Detection
    # ──────────────────────────────────────────────────────────────────
    @classmethod
    def detect_command(cls, message: str, require_prefix: bool = False) -> Optional[GovernanceCommand]:
        """Parse a message into a GovernanceCommand, or None if no directive.

        Args:
            message: raw text to inspect.
            require_prefix: when True, the directive phrase must START the
                (stripped, lowercased) message. Used for inter-agent routing
                where messages are free-form prose (task outputs, critic
                reviews) and a phrase appearing mid-sentence must NOT be
                mistaken for a command. The Sovereign chat path passes False so
                polite phrasings ("please spawn a task agent") still match.
        """
        if not message or not message.strip():
            return None

        lowered = message.lower().strip()

        def _matches(phrase: str) -> bool:
            return lowered.startswith(phrase) if require_prefix else phrase in lowered

        # Task/lead agent provisioning takes precedence over the more generic
        # "create a task" phrase (which is a substring of "create a task agent").
        if any(_matches(phrase) for phrase in cls.TASK_PHRASES):
            name, description = cls._extract_name_and_desc(message)
            return GovernanceCommand(
                kind="spawn_task_agent",
                name=name,
                description=description,
            )

        if any(_matches(phrase) for phrase in cls.LEAD_PHRASES):
            name, description = cls._extract_name_and_desc(message)
            return GovernanceCommand(
                kind="spawn_lead_agent",
                name=name,
                description=description,
            )

        if any(_matches(phrase) for phrase in cls.CREATE_TASK_PHRASES):
            return GovernanceCommand(
                kind="create_task",
                description=message.strip(),
            )

        return None

    @classmethod
    def _extract_name_and_desc(cls, message: str) -> Tuple[Optional[str], str]:
        """Extract an optional agent name and always return the full description."""
        name: Optional[str] = None
        match = cls._NAME_RE.search(message)
        if match:
            candidate = match.group(1).strip().rstrip(".").strip()
            if candidate and candidate.lower() not in ("task agent", "lead agent", "a"):
                name = candidate
        return name, message.strip()

    # ──────────────────────────────────────────────────────────────────
    # Execution
    # ──────────────────────────────────────────────────────────────────
    @classmethod
    def execute(cls, command: GovernanceCommand, actor: Agent, db: Session) -> dict:
        """Dispatch a parsed command to its executor."""
        if command.kind == "spawn_task_agent":
            return cls._spawn_task_agent(command, actor, db)
        if command.kind == "spawn_lead_agent":
            return cls._spawn_lead_agent(command, actor, db)
        if command.kind == "create_task":
            return cls._create_task(command, actor, db)
        raise ValueError(f"Unknown governance command kind: {command.kind!r}")

    @classmethod
    def _spawn_task_agent(cls, command: GovernanceCommand, actor: Agent, db: Session) -> dict:
        # Authority gate (defence-in-depth; reincarnation service checks too).
        if not CapabilityRegistry.can_agent(actor, Capability.SPAWN_TASK_AGENT, db):
            raise PermissionError(
                f"Agent {actor.agentium_id} lacks authority to spawn Task Agents "
                "(requires SPAWN_TASK_AGENT capability)."
            )

        parent = cls._resolve_task_parent(actor, db)

        agent = reincarnation_service.spawn_task_agent(
            parent=parent,
            name=command.name or f"Task Agent {parent.agentium_id}",
            description=command.description or "Task agent provisioned via directive.",
            capabilities=command.capabilities,
            db=db,
        )
        db.commit()

        return {
            "action": "spawn_task_agent",
            "agentium_id": agent.agentium_id,
            "parent_id": parent.agentium_id,
            "agent_type": "task_agent",
            "content": (
                f"Task Agent {agent.agentium_id} ('{agent.name}') has been spawned "
                f"under {parent.agentium_id}."
            ),
        }

    @classmethod
    def _spawn_lead_agent(cls, command: GovernanceCommand, actor: Agent, db: Session) -> dict:
        # Authority gate.
        if not CapabilityRegistry.can_agent(actor, Capability.SPAWN_LEAD, db):
            raise PermissionError(
                f"Agent {actor.agentium_id} lacks authority to spawn Lead Agents "
                "(requires SPAWN_LEAD capability)."
            )

        head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        if head is None:
            raise ValueError("Head of Council (00001) not found; cannot spawn Lead Agent.")

        agent = reincarnation_service.spawn_lead_agent(
            parent=head,
            name=command.name or "Lead Agent",
            description=command.description or "Lead agent provisioned via directive.",
            db=db,
        )
        db.commit()

        return {
            "action": "spawn_lead_agent",
            "agentium_id": agent.agentium_id,
            "parent_id": head.agentium_id,
            "agent_type": "lead_agent",
            "content": (
                f"Lead Agent {agent.agentium_id} ('{agent.name}') has been spawned "
                f"under the Head of Council ({head.agentium_id})."
            ),
        }

    @classmethod
    def _resolve_task_parent(cls, actor: Agent, db: Session) -> Agent:
        """Resolve the parent under which a task agent should be spawned."""
        # A Lead Agent spawns Task Agents under itself.
        if isinstance(actor, LeadAgent):
            return actor

        # Head/Council: prefer the first active Lead Agent, else the actor itself.
        lead = (
            db.query(LeadAgent)
            .filter(LeadAgent.status == AgentStatus.ACTIVE)
            .first()
        )
        return lead or actor

    @classmethod
    def _create_task(cls, command: GovernanceCommand, actor: Agent, db: Session) -> dict:
        head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()

        task = Task(
            title=(command.description or "Directive task")[:120],
            description=command.description or "Task provisioned via directive.",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            created_by=actor.agentium_id,
            head_of_council_id=head.id if head else None,
            requires_deliberation=True,
        )
        db.add(task)
        db.commit()

        # If a Council exists, kick off deliberation.
        council = db.query(CouncilMember).all()
        if council:
            task.start_deliberation([c.agentium_id for c in council])
            db.commit()

        return {
            "action": "create_task",
            "task_id": task.agentium_id,
            "content": f"Task {task.agentium_id} has been created.",
        }

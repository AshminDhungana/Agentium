"""
Governance tools — LLM-callable wrappers over the canonical service layer.

Every wrapper declares `db` and `agent_id` so ToolCreationService.execute_tool
injects them automatically (inspect-based). Each returns a uniform dict:
    {"success": bool, "data": dict|None, "error": str|None}

Authority is enforced by CapabilityRegistry (defence-in-depth; the underlying
services also raise PermissionError). Tools are registered in
backend.core.tool_registry.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.models.entities.agents import (
    Agent,
    AgentType,
    CouncilMember,
    HeadOfCouncil,
    LeadAgent,
    TaskAgent,
)
from backend.services.capability_registry import Capability, CapabilityRegistry
from backend.services.reincarnation_service import reincarnation_service
from backend.models.entities.task import Task, TaskType, TaskPriority, TaskStatus
from backend.services.agent_orchestrator import AgentOrchestrator

logger = logging.getLogger(__name__)


def _result(success: bool, data: Optional[dict] = None, error: Optional[str] = None) -> Dict[str, Any]:
    return {"success": success, "data": data, "error": error}


def _caller(db: Session, agent_id: str) -> Optional[Agent]:
    return db.query(Agent).filter(Agent.agentium_id == agent_id).first()


def _require(cap: Capability, caller: Agent, db: Session, label: str) -> Optional[Dict[str, Any]]:
    if not CapabilityRegistry.can_agent(caller, cap, db):
        return _result(False, error=f"not authorized: {label} requires {cap.value}")
    return None


def spawn_agent(
    agent_type: str,
    name: str,
    description: str,
    capabilities: Optional[List[str]] = None,
    db: Session = None,
    agent_id: str = None,
) -> Dict[str, Any]:
    caller = _caller(db, agent_id) if db and agent_id else None
    if caller is None:
        return _result(False, error="caller agent not found")

    atype = (agent_type or "").lower()
    if atype == "council":
        denied = _require(Capability.SPAWN_COUNCIL, caller, db, "spawn council")
        if denied:
            return denied
        head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        if head is None:
            return _result(False, error="Head of Council not found")
        new_agent = head.spawn_child(AgentType.COUNCIL_MEMBER, db,
                                     name=name, description=description)
        db.add(new_agent)
        db.commit()
        return _result(True, data={"agentium_id": new_agent.agentium_id,
                                  "agent_type": AgentType.COUNCIL_MEMBER.value,
                                  "name": name})
    if atype == "lead":
        denied = _require(Capability.SPAWN_LEAD, caller, db, "spawn lead")
        if denied:
            return denied
        try:
            new_agent = reincarnation_service.spawn_lead_agent(
                parent=caller, name=name, description=description, db=db
            )
        except PermissionError as e:
            return _result(False, error=str(e))
        return _result(True, data={"agentium_id": new_agent.agentium_id,
                                  "agent_type": AgentType.LEAD_AGENT.value,
                                  "name": name})
    if atype == "task":
        denied = _require(Capability.SPAWN_TASK_AGENT, caller, db, "spawn task")
        if denied:
            return denied
        try:
            new_agent = reincarnation_service.spawn_task_agent(
                parent=caller, name=name, description=description,
                capabilities=capabilities, db=db
            )
        except PermissionError as e:
            return _result(False, error=str(e))
        return _result(True, data={"agentium_id": new_agent.agentium_id,
                                  "agent_type": AgentType.TASK_AGENT.value,
                                  "name": name})
    return _result(False, error=f"unknown agent_type '{agent_type}' (expected council|lead|task)")


def liquidate_agent(
    target_agentium_id: str,
    reason: str,
    db: Session = None,
    agent_id: str = None,
) -> Dict[str, Any]:
    caller = _caller(db, agent_id) if db and agent_id else None
    if caller is None:
        return _result(False, error="caller agent not found")
    if target_agentium_id == "00001":
        return _result(False, error="cannot liquidate the Head of Council")

    target = db.query(Agent).filter(Agent.agentium_id == target_agentium_id).first()
    if target is None:
        return _result(False, error=f"target agent {target_agentium_id} not found")

    if caller.agentium_id.startswith("0"):
        cap = Capability.LIQUIDATE_ANY
    elif caller.agentium_id.startswith("2") and target.agentium_id.startswith(("3", "4", "5", "6")):
        cap = Capability.LIQUIDATE_TASK_AGENT
    else:
        return _result(False, error="not authorized: caller cannot liquidate this agent")
    denied = _require(cap, caller, db, "liquidate")
    if denied:
        return denied
    try:
        outcome = reincarnation_service.liquidate_agent(
            agent_id=target_agentium_id, liquidated_by=caller,
            reason=reason, db=db
        )
    except PermissionError as e:
        return _result(False, error=str(e))
    return _result(True, data=outcome if isinstance(outcome, dict) else {"status": "liquidated"})


def create_task(
    title: str,
    description: str,
    priority: str = "normal",
    db: Session = None,
    agent_id: str = None,
) -> Dict[str, Any]:
    caller = _caller(db, agent_id) if db and agent_id else None
    if caller is None:
        return _result(False, error="caller agent not found")
    denied = _require(Capability.DELEGATE_WORK, caller, db, "create task")
    if denied:
        return denied

    head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    try:
        prio = TaskPriority(priority.lower())
    except ValueError:
        prio = TaskPriority.NORMAL
    task = Task(
        title=(title or description)[:200],
        description=description or title or "Task provisioned via tool.",
        task_type=TaskType.EXECUTION,
        priority=prio,
        created_by=caller.agentium_id,
        head_of_council_id=head.id if head else None,
        requires_deliberation=True,
    )
    db.add(task)
    db.commit()
    council = db.query(CouncilMember).all()
    if council:
        task.start_deliberation([c.agentium_id for c in council])
        db.commit()
    return _result(True, data={"task_id": task.agentium_id, "status": task.status.value})


async def dispatch_task(
    task_id: str,
    target_agentium_id: Optional[str] = None,
    db: Session = None,
    agent_id: str = None,
) -> Dict[str, Any]:
    caller = _caller(db, agent_id) if db and agent_id else None
    if caller is None:
        return _result(False, error="caller agent not found")
    denied = _require(Capability.DELEGATE_WORK, caller, db, "dispatch task")
    if denied:
        return denied

    task = db.query(Task).filter(Task.agentium_id == task_id).first()
    if task is None:
        return _result(False, error=f"task {task_id} not found")

    if target_agentium_id:
        lead = db.query(LeadAgent).filter(LeadAgent.agentium_id == target_agentium_id).first()
        if lead is None:
            return _result(False, error=f"lead agent {target_agentium_id} not found")
    else:
        lead = db.query(LeadAgent).filter(LeadAgent.status == "active").first()
    if lead is None:
        return _result(False, error="no available Lead agent to dispatch to")

    orchestrator = AgentOrchestrator(db)
    task_dict = {
        "id": task.id,
        "task_type": task.task_type.value if task.task_type else "general",
        "description": task.description or "",
        "allowed_tools": task.tools_allowed or [],
    }
    try:
        outcome = await orchestrator.delegate_to_task(
            task=task_dict,
            lead_id=lead.agentium_id,
            task_id=None,
            retry_count=0,
        )
    except Exception as e:
        return _result(False, error=str(e))
    return _result(True, data={"task_id": task.agentium_id,
                              "lead_id": lead.agentium_id,
                              "outcome": str(outcome)})


def complete_task(
    task_id: str,
    result_summary: str,
    db: Session = None,
    agent_id: str = None,
) -> Dict[str, Any]:
    caller = _caller(db, agent_id) if db and agent_id else None
    if caller is None:
        return _result(False, error="caller agent not found")
    denied = _require(Capability.EXECUTE_TASK, caller, db, "complete task")
    if denied:
        return denied

    task = db.query(Task).filter(Task.agentium_id == task_id).first()
    if task is None:
        return _result(False, error=f"task {task_id} not found")
    try:
        task.complete(result_summary=result_summary, result_data={})
        db.commit()
    except Exception as e:
        return _result(False, error=str(e))
    return _result(True, data={"task_id": task.agentium_id, "status": task.status.value})

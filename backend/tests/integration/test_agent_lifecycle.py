import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from backend.models.entities.agents import Agent, AgentStatus, AgentType, CouncilMember, HeadOfCouncil
from backend.models.entities.constitution import Ethos
from backend.models.entities.task import Task, TaskStatus, TaskPriority, TaskType
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.services.reincarnation_service import reincarnation_service
from backend.services.idle_governance import idle_governance

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_agent_lifecycle_full_flow(seeded_db: Session):
    """
    Verify full agent lifecycle:
    spawn -> assign task -> complete task -> verify ethos update ->
    idle 7-day simulation -> auto-termination;
    assert every state transition writes an AuditLog entry with correct category and level.
    """
    # 1. Resolve parent Council Member (1xxxx) seeded during Genesis protocol
    parent = seeded_db.query(CouncilMember).first()
    assert parent is not None, "A Council Member must be seeded by default."

    # 2. Spawn Task Agent (3xxxx) under Council Member parent
    task_agent = reincarnation_service.spawn_task_agent(
        parent=parent,
        name="Lifecycle Worker Agent",
        description="Task agent dedicated to testing lifecycle flow.",
        capabilities=["mcp_tool_execution"],
        db=seeded_db
    )
    seeded_db.commit()

    # Assert spawn results
    assert task_agent is not None
    assert task_agent.agent_type == AgentType.TASK_AGENT
    assert task_agent.status == AgentStatus.ACTIVE
    assert task_agent.is_active is True
    assert task_agent.ethos_id is not None

    # Assert spawn audit log (category = GOVERNANCE, level = INFO)
    spawn_audit = seeded_db.query(AuditLog).filter(
        AuditLog.action == "agent_spawned",
        AuditLog.target_id == task_agent.agentium_id
    ).first()
    assert spawn_audit is not None, "Audit log for agent spawning must be created."
    assert spawn_audit.category == AuditCategory.GOVERNANCE
    assert spawn_audit.level == AuditLevel.INFO
    assert spawn_audit.actor_id == parent.agentium_id

    # 3. Assign Task to Agent
    task = Task(
        agentium_id="TTESTLF99",
        title="Integration Testing Lifecycle Task",
        description="Assigned task for testing the post-task ritual and ethos compression.",
        task_type=TaskType.EXECUTION,
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.LOW,
        assigned_task_agent_ids=[task_agent.agentium_id],
        is_idle_task=False,
        is_active=True,
        supervisor_id=parent.agentium_id,
        created_by=parent.agentium_id
    )
    seeded_db.add(task)
    seeded_db.commit()

    # 4. Complete Task and Run Post-Task Recalibration Ritual
    outcome = "Successful execution of the test workload."
    lessons = [{"key_point": "State transitions must be deterministic", "severity": "low"}]
    
    ritual_results = task_agent.post_task_ritual(
        db=seeded_db,
        outcome_summary=outcome,
        lessons=lessons
    )
    
    # Assert post-task ritual results
    assert ritual_results["outcome_recorded"] is True
    assert ritual_results["lessons_recorded"] == 1
    assert ritual_results["ethos_compressed"] is True
    assert ritual_results["working_state_reset"] is True

    # Assert post-task audit log (category = GOVERNANCE, level = INFO)
    recal_audit = seeded_db.query(AuditLog).filter(
        AuditLog.action == "post_task_recalibration",
        AuditLog.actor_id == task_agent.agentium_id
    ).first()
    assert recal_audit is not None, "Audit log for post-task recalibration must be created."
    assert recal_audit.category == AuditCategory.GOVERNANCE
    assert recal_audit.level == AuditLevel.INFO

    # 5. Verify Ethos Update
    ethos = seeded_db.query(Ethos).filter_by(id=task_agent.ethos_id).first()
    assert ethos is not None
    assert ethos.outcome_summary == outcome
    
    recorded_lessons = ethos.get_lessons_learned()
    assert len(recorded_lessons) == 1
    assert recorded_lessons[0]["key_point"] == "State transitions must be deterministic"
    
    # Execution plan and object state should be reset/pruned
    assert ethos.active_plan is None
    assert ethos.task_progress_markers is None
    assert ethos.current_objective is None

    # 6. Simulate 7-day Idle Period
    # Mark the task as completed to ensure the agent has no active tasks
    task.status = TaskStatus.COMPLETED
    task.is_active = False
    
    # Backdate last action to exceed 7-day idle threshold
    eight_days_ago = datetime.utcnow() - timedelta(days=8)
    task_agent.last_idle_action_at = eight_days_ago
    task_agent.status = AgentStatus.ACTIVE
    task_agent.is_active = True
    seeded_db.commit()

    # Protect the seeded/founding agents from the idle auto-liquidator so this
    # test only observes the lifecycle of its own spawned task agent.
    for ag in seeded_db.query(Agent).filter(
        Agent.agentium_id != task_agent.agentium_id
    ).all():
        ag.is_persistent = True
    seeded_db.flush()

    # 7. Execute Auto-Termination (Auto-Liquidation)
    liquidation_summary = await idle_governance.auto_liquidate_expired(seeded_db)
    
    # Assert liquidation execution
    assert liquidation_summary["liquidated_count"] == 1
    assert task_agent.agentium_id in liquidation_summary["liquidated"]

    # Assert agent is terminated
    seeded_db.refresh(task_agent)
    assert task_agent.is_active is False
    assert task_agent.status == AgentStatus.TERMINATED
    assert "Auto-liquidation" in task_agent.termination_reason

    # Assert liquidation audit log (category = GOVERNANCE, level = WARNING)
    liquidation_audit = seeded_db.query(AuditLog).filter(
        AuditLog.action == "agent_liquidated",
        AuditLog.target_id == task_agent.agentium_id
    ).first()
    assert liquidation_audit is not None, "Audit log for agent liquidation must be created."
    assert liquidation_audit.category == AuditCategory.GOVERNANCE
    assert liquidation_audit.level == AuditLevel.WARNING
    assert liquidation_audit.actor_id == "00001"  # Under Head authority
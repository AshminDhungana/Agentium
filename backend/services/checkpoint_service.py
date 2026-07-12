"""
CheckpointService for Agentium.

Handles the creation, retrieval, and application of checkpoints
for Phase 6.5 Time-Travel and Branching functionality.

Improvements (from verification review):
  - create_checkpoint() now serialises real agent_states
  - resume_from_checkpoint() restores full relational state
"""

from typing import Optional, Dict, List, Any, Tuple 
from datetime import datetime, timedelta
import uuid
import logging
import json
import hashlib

from sqlalchemy.orm import Session
from backend.models.entities.checkpoint import ExecutionCheckpoint, CheckpointPhase
from backend.models.entities.task import Task, TaskStatus
from backend.models.entities.agents import Agent, AgentStatus
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory

logger = logging.getLogger(__name__)


class CheckpointService:
    """
    Manages state snapshots for tasks, allowing resumption, 
    retry from past states, and divergent branching.
    """

    # ═══════════════════════════════════════════════════════════
    # CHECKPOINT CREATION
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def create_checkpoint(
        db: Session,
        task_id: str,
        phase: CheckpointPhase,
        actor_id: str = "system",
        artifacts: Optional[List[Dict[str, Any]]] = None
    ) -> ExecutionCheckpoint:
        """
        Takes a snapshot of complete system state for a given task.
        Extracts subtasks, agent assignments, and agent states.
        """
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found.")

        # Serialize current task state
        task_snapshot = task.to_dict()

        # ── Serialize assigned agent states ──────────────────────
        agent_states = CheckpointService._capture_agent_states(db, task)

        # ── Serialize subtask states ─────────────────────────────
        subtask_snapshots = CheckpointService._capture_subtasks(db, task)
        task_snapshot["subtask_snapshots"] = subtask_snapshots

        checkpoint = ExecutionCheckpoint(
            id=str(uuid.uuid4()),
            session_id=task.workflow_id or "no-workflow",
            task_id=task.id,
            phase=phase,
            agent_states=agent_states,
            artifacts=artifacts or [],
            task_state_snapshot=task_snapshot
        )

        db.add(checkpoint)
        
        audit_entry = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.SYSTEM,
            actor_type="system",
            actor_id=actor_id,
            action="checkpoint_created",
            target_type="checkpoint",
            target_id=checkpoint.id,
            description=(
                f"Checkpoint created for task {task_id} at phase {phase.value} "
                f"({len(agent_states)} agents, {len(subtask_snapshots)} subtasks)"
            )
        )
        db.add(audit_entry)
        
        db.commit()
        db.refresh(checkpoint)
        return checkpoint

    # ═══════════════════════════════════════════════════════════
    # TIME TRAVEL (RESUME)
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def resume_from_checkpoint(
        db: Session,
        checkpoint_id: str,
        actor_id: str = "user"
    ) -> Task:
        """
        Restores a task's full relational state to match the given checkpoint.
        Restores: task status, result_data, agent assignments, subtask states.
        """
        checkpoint = db.query(ExecutionCheckpoint).filter(
            ExecutionCheckpoint.id == checkpoint_id
        ).first()
        if not checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_id} not found.")

        task = db.query(Task).filter(Task.id == checkpoint.task_id).first()
        if not task:
            raise ValueError(f"Task {checkpoint.task_id} not found.")

        snapshot = checkpoint.task_state_snapshot

        # ── 1. Restore task core properties ──────────────────────
        if 'status' in snapshot:
            restored_status = TaskStatus(snapshot['status'])
            if task.status != restored_status:
                task.set_status(
                    restored_status,
                    actor_id=actor_id,
                    note=f"Resumed from checkpoint {checkpoint_id}",
                    trigger_checkpoint=False,
                )
            
        if 'result_data' in snapshot:
            task.result_data = snapshot['result_data']

        if 'assigned_task_agent_ids' in snapshot:
            task.assigned_task_agent_ids = snapshot['assigned_task_agent_ids']

        if 'completion_summary' in snapshot:
            task.completion_summary = snapshot.get('completion_summary')

        # ── 2. Restore agent states ──────────────────────────────
        CheckpointService._restore_agent_states(db, checkpoint.agent_states)

        # ── 3. Restore subtask states ────────────────────────────
        subtask_snapshots = snapshot.get("subtask_snapshots", [])
        CheckpointService._restore_subtasks(db, subtask_snapshots, actor_id, checkpoint_id)

        audit_entry = AuditLog.log(
            level=AuditLevel.WARNING,
            category=AuditCategory.SYSTEM,
            actor_type="user",
            actor_id=actor_id,
            action="checkpoint_resumed",
            target_type="task",
            target_id=task.id,
            description=(
                f"Task {task.id} time-travelled to checkpoint {checkpoint_id} "
                f"(restored {len(checkpoint.agent_states)} agents, "
                f"{len(subtask_snapshots)} subtasks)"
            )
        )
        db.add(audit_entry)

        db.commit()
        db.refresh(task)
        return task

    # ═══════════════════════════════════════════════════════════
    # BRANCHING
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def branch_from_checkpoint(
        db: Session,
        checkpoint_id: str,
        branch_name: str,
        new_supervisor_id: Optional[str] = None,
        actor_id: str = "user"
    ) -> Task:
        """
        Creates a clone task from a specific checkpoint's state to allow
        parallel execution strategies without altering the original flow.
        """
        checkpoint = db.query(ExecutionCheckpoint).filter(
            ExecutionCheckpoint.id == checkpoint_id
        ).first()
        if not checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_id} not found.")

        snapshot = checkpoint.task_state_snapshot
        
        # Create a new branch task avoiding unique constraints
        new_task_id = str(uuid.uuid4())
        
        new_task = Task(
            id=new_task_id,
            description=snapshot.get('description'),
            supervisor_id=new_supervisor_id or snapshot.get('supervisor_id'),
            priority=snapshot.get('priority'),
            type=snapshot.get('type'),
            session_id=snapshot.get('session_id'),
            acceptance_criteria=snapshot.get('acceptance_criteria'),
            veto_authority=snapshot.get('veto_authority'),
            input_data=snapshot.get('input_data')
        )

        db.add(new_task)
        
        # Create a branch checkpoint
        branch_checkpoint = ExecutionCheckpoint(
            id=str(uuid.uuid4()),
            session_id=new_task.session_id,
            task_id=new_task.id,
            phase=checkpoint.phase,
            agent_states=checkpoint.agent_states,
            artifacts=checkpoint.artifacts,
            task_state_snapshot=new_task.to_dict(),
            parent_checkpoint_id=checkpoint.id,
            branch_name=branch_name
        )
        db.add(branch_checkpoint)

        audit_entry = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.TASK,
            actor_type="user",
            actor_id=actor_id,
            action="checkpoint_branched",
            target_type="task",
            target_id=new_task.id,
            description=f"Branched from checkpoint {checkpoint_id} into new task {new_task.id}"
        )
        db.add(audit_entry)

        db.commit()
        db.refresh(new_task)
        return new_task

    # ═══════════════════════════════════════════════════════════
    # CLEANUP
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def cleanup_old_checkpoints(db: Session, max_age_days: int = 90) -> int:
        """
        Purges execution checkpoints older than a specific age threshold.
        By default, cleans up checkpoints older than 90 days.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
        
        checkpoints_to_delete = db.query(ExecutionCheckpoint).filter(
            ExecutionCheckpoint.created_at < cutoff_date
        ).all()
        
        count = len(checkpoints_to_delete)
        for ck in checkpoints_to_delete:
            db.delete(ck)
            
        if count > 0:
            audit_entry = AuditLog.log(
                level=AuditLevel.INFO,
                category=AuditCategory.SYSTEM,
                actor_type="system",
                actor_id="cleanup_cron",
                action="checkpoint_cleanup",
                description=f"Deleted {count} checkpoints older than {max_age_days} days"
            )
            db.add(audit_entry)
            db.commit()
            
        return count

    # ═══════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _capture_agent_states(db: Session, task: Task) -> Dict[str, Any]:
        """
        Serialize the current state of every agent assigned to this task.
        Captures: status, current_task_id, ethos summary, capabilities.
        """
        agent_states: Dict[str, Any] = {}
        assigned_ids = task.assigned_task_agent_ids or []

        # Also include the supervisor
        all_ids = list(set(assigned_ids + ([task.supervisor_id] if task.supervisor_id else [])))

        for agentium_id in all_ids:
            agent = db.query(Agent).filter_by(agentium_id=agentium_id, is_active=True).first()
            if not agent:
                continue

            agent_states[agentium_id] = {
                "status": agent.status.value if agent.status else None,
                "current_task_id": agent.current_task_id,
                "agent_type": agent.agent_type.value if agent.agent_type else None,
                "is_persistent": agent.is_persistent,
                "ethos_summary": (
                    agent.ethos.mission_statement[:500]
                    if hasattr(agent, 'ethos') and agent.ethos and agent.ethos.mission_statement
                    else None
                ),
                "custom_capabilities": agent.custom_capabilities if hasattr(agent, 'custom_capabilities') else None,
                "last_idle_action_at": (
                    agent.last_idle_action_at.isoformat() if agent.last_idle_action_at else None
                ),
            }

        return agent_states

    @staticmethod
    def _capture_subtasks(db: Session, task: Task) -> List[Dict[str, Any]]:
        """Serialize all subtasks of the given parent task."""
        subtasks = db.query(Task).filter(
            Task.parent_task_id == task.id,
            Task.is_active == True
        ).all()

        return [
            {
                "id": str(st.id),
                "status": st.status.value if st.status else None,
                "description": st.description,
                "assigned_task_agent_ids": st.assigned_task_agent_ids,
                "result_data": st.result_data,
                "completion_summary": st.completion_summary,
            }
            for st in subtasks
        ]

    @staticmethod
    def _restore_agent_states(db: Session, agent_states: Dict[str, Any]):
        """Restore agent statuses and current_task assignments from snapshot."""
        for agentium_id, state in (agent_states or {}).items():
            agent = db.query(Agent).filter_by(agentium_id=agentium_id, is_active=True).first()
            if not agent:
                logger.warning(f"⚠️ Agent {agentium_id} not found during checkpoint restore, skipping")
                continue

            saved_status = state.get("status")
            if saved_status:
                try:
                    agent.status = AgentStatus(saved_status)
                except ValueError:
                    pass

            saved_task = state.get("current_task_id")
            agent.current_task_id = saved_task

    @staticmethod
    def _restore_subtasks(
        db: Session,
        subtask_snapshots: List[Dict[str, Any]],
        actor_id: str,
        checkpoint_id: str,
    ):
        """Restore subtask statuses and result data from snapshot."""
        for snap in subtask_snapshots:
            subtask = db.query(Task).filter(Task.id == snap.get("id")).first()
            if not subtask:
                continue

            saved_status = snap.get("status")
            if saved_status:
                try:
                    restored_status = TaskStatus(saved_status)
                    if subtask.status != restored_status:
                        subtask.set_status(
                            restored_status,
                            actor_id=actor_id,
                            note=f"Restored from checkpoint {checkpoint_id}",
                            trigger_checkpoint=False,
                        )
                except (ValueError, Exception) as e:
                    logger.warning(
                        f"⚠️ Failed to restore status '{saved_status}' for subtask "
                        f"{snap.get('id')} during checkpoint restore: {e}"
                    )

            if "result_data" in snap:
                subtask.result_data = snap["result_data"]

            if "assigned_task_agent_ids" in snap:
                subtask.assigned_task_agent_ids = snap["assigned_task_agent_ids"]

            if "completion_summary" in snap:
                subtask.completion_summary = snap.get("completion_summary")



    # ═══════════════════════════════════════════════════════════
    # PHASE 7: IMPORT / EXPORT OPERATIONS
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def export_checkpoint(db: Session, checkpoint_id: str) -> Dict[str, Any]:
        """
        Prepare checkpoint for export with integrity metadata.
        """
        checkpoint = db.query(ExecutionCheckpoint).filter(
            ExecutionCheckpoint.id == checkpoint_id
        ).first()

        if not checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")

        export_data = {
            'checkpoint': checkpoint.to_dict(),
            'exported_at': datetime.utcnow().isoformat(),
            'version': '1.0',
        }

        # Generate checksum for integrity verification
        checksum_data = json.dumps(export_data, sort_keys=True, separators=(',', ':'))
        export_data['checksum'] = hashlib.sha256(checksum_data.encode()).hexdigest()[:16]

        return export_data

    @staticmethod
    def validate_import_data(data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """
        Validate imported checkpoint data.
        Returns: (is_valid, errors, warnings)
        """
        errors = []
        warnings = []

        # Check version compatibility
        version = data.get('version', 'unknown')
        if version not in ['1.0']:
            warnings.append(f"Version {version} may have compatibility issues")

        # Verify checksum if present
        if 'checksum' in data:
            stored_checksum = data.pop('checksum')
            computed = hashlib.sha256(
                json.dumps(data, sort_keys=True, separators=(',', ':')).encode()
            ).hexdigest()[:16]

            if stored_checksum != computed:
                errors.append("Checksum mismatch - data may be corrupted")

        # Validate checkpoint structure
        cp = data.get('checkpoint', {})
        required_fields = ['id', 'task_id', 'phase', 'agent_states', 'task_state_snapshot']

        for field in required_fields:
            if field not in cp:
                errors.append(f"Missing required field: {field}")

        # Validate phase value
        if 'phase' in cp:
            try:
                CheckpointPhase(cp['phase'])
            except ValueError:
                errors.append(f"Invalid phase value: {cp['phase']}")

        return len(errors) == 0, errors, warnings

    @staticmethod
    def import_checkpoint(
        db: Session,
        data: Dict[str, Any],
        target_branch: Optional[str] = None,
        conflict_resolution: str = 'rename',
        actor_id: str = 'system'
    ) -> Tuple[ExecutionCheckpoint, List[Dict[str, str]]]:
        """
        Import checkpoint with conflict resolution.
        Returns: (checkpoint, conflicts)
        """
        conflicts = []
        checkpoint_data = data['checkpoint']

        # Handle ID conflicts
        existing_id = db.query(ExecutionCheckpoint).filter(
            ExecutionCheckpoint.id == checkpoint_data['id']
        ).first()

        final_id = checkpoint_data['id']
        if existing_id:
            if conflict_resolution == 'skip':
                raise ValueError(f"Checkpoint {final_id} already exists")
            elif conflict_resolution == 'replace':
                db.delete(existing_id)
                db.flush()
            elif conflict_resolution == 'rename':
                final_id = f"{checkpoint_data['id']}_import_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
                conflicts.append({
                    'type': 'id_collision',
                    'message': f"Renamed to {final_id}",
                    'resolution': 'rename'
                })

        # Handle branch name
        branch = target_branch or checkpoint_data.get('branch_name') or 'imported'
        if conflict_resolution == 'rename':
            branch_exists = db.query(ExecutionCheckpoint).filter(
                ExecutionCheckpoint.branch_name == branch
            ).first()
            if branch_exists:
                branch = f"{branch}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
                conflicts.append({
                    'type': 'branch_conflict',
                    'message': f"Branch renamed to {branch}",
                    'resolution': 'rename'
                })

        # Create checkpoint
        new_checkpoint = ExecutionCheckpoint(
            id=final_id,
            session_id=checkpoint_data.get('session_id', f"import_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"),
            task_id=checkpoint_data['task_id'],
            phase=CheckpointPhase(checkpoint_data['phase']),
            agent_states=checkpoint_data.get('agent_states', {}),
            artifacts=checkpoint_data.get('artifacts', []),
            task_state_snapshot=checkpoint_data.get('task_state_snapshot', {}),
            parent_checkpoint_id=checkpoint_data.get('parent_checkpoint_id'),
            branch_name=branch,
            is_active=True
        )

        db.add(new_checkpoint)
        db.commit()
        db.refresh(new_checkpoint)

        return new_checkpoint, conflicts
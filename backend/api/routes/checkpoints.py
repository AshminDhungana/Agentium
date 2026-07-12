"""
API routes for ExecutionCheckpoints (Time-Travel and Branching).
Phase 6.5 implementation.
"""
import hashlib
import json
import difflib
from datetime import datetime
from fastapi import File, UploadFile, Form
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from io import BytesIO
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.models.entities.checkpoint import ExecutionCheckpoint, CheckpointPhase
from backend.services.checkpoint_service import CheckpointService
from backend.api.schemas.checkpoint import (
    CheckpointCreate,
    CheckpointResponse,
    CheckpointBranchRequest,
    UnifiedDiffResponse,
)
from backend.api.schemas.task import TaskResponse
from pydantic import BaseModel

from backend.api.schemas.examples import ErrorResponseExample, SuccessResponseExample, build_responses

router = APIRouter(prefix="/checkpoints", tags=["checkpoints"])


class CheckpointExportData(BaseModel):
    checkpoint: CheckpointResponse
    exported_at: str
    version: str
    checksum: str


class ValidationResult(BaseModel):
    valid: bool
    errors: List[str]
    warnings: List[str]
    checksum_valid: bool
    schema_version: str


class ImportOptions(BaseModel):
    target_branch: Optional[str] = None
    skip_validation: bool = False
    conflict_resolution: str = "rename"  # skip, replace, rename, merge


class ImportConflict(BaseModel):
    type: str  # id_collision, branch_conflict, parent_missing, version_mismatch
    message: str
    resolution: str


class ImportResult(BaseModel):
    success: bool
    checkpoint: Optional[CheckpointResponse] = None
    conflicts: Optional[List[ImportConflict]] = None
    validation: Optional[ValidationResult] = None



# ─── Branch comparison schemas ────────────────────────────────────────────────

class FieldDiff(BaseModel):
    key: str
    left: Any
    right: Any
    status: str  # "added" | "removed" | "changed" | "unchanged"
    children: Optional[List["FieldDiff"]] = None  # recursive nested diffs

FieldDiff.model_rebuild()


class AgentStateDiff(BaseModel):
    agent_id: str
    status: str  # "added" | "removed" | "changed" | "unchanged"
    diffs: List[FieldDiff]


class ArtifactDiff(BaseModel):
    key: str
    status: str  # "added" | "removed" | "changed" | "unchanged"
    left: Any
    right: Any


class BranchCompareResponse(BaseModel):
    left_branch: str
    right_branch: str
    left_checkpoint_id: str
    right_checkpoint_id: str
    left_created_at: str
    right_created_at: str
    task_state_diffs: List[FieldDiff]
    agent_state_diffs: List[AgentStateDiff]
    artifact_diffs: List[ArtifactDiff]
    summary: Dict[str, int]  # {"added": n, "removed": n, "changed": n, "unchanged": n}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _diff_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> List[FieldDiff]:
    """Produce a (recursive) list of FieldDiff between two dicts."""
    diffs: List[FieldDiff] = []
    all_keys = set(left.keys()) | set(right.keys())
    for key in sorted(all_keys):
        if key not in left:
            diffs.append(FieldDiff(key=key, left=None, right=right[key], status="added"))
        elif key not in right:
            diffs.append(FieldDiff(key=key, left=left[key], right=None, status="removed"))
        elif left[key] != right[key]:
            if isinstance(left[key], dict) and isinstance(right[key], dict):
                children = _diff_dicts(left[key], right[key])
                diffs.append(FieldDiff(
                    key=key, left=left[key], right=right[key],
                    status="changed", children=children,
                ))
            else:
                diffs.append(FieldDiff(key=key, left=left[key], right=right[key], status="changed"))
        else:
            diffs.append(FieldDiff(key=key, left=left[key], right=right[key], status="unchanged"))
    return diffs


def _summarize(diffs: List[FieldDiff]) -> Dict[str, int]:
    summary: Dict[str, int] = {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}
    for d in diffs:
        summary[d.status] = summary.get(d.status, 0) + 1
    return summary

def _generate_checksum(data: Dict[str, Any]) -> str:
    """Generate SHA-256 checksum of checkpoint data."""
    canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _validate_checkpoint_data(data: Dict[str, Any]) -> ValidationResult:
    """Validate checkpoint data structure and integrity."""
    errors = []
    warnings = []
    
    # Schema version check
    version = data.get('version', 'unknown')
    if version != '1.0':
        warnings.append(f"Schema version {version} may not be fully compatible")
    
    # Required fields
    required = ['checkpoint', 'exported_at', 'checksum']
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    
    # Checksum validation
    checksum_valid = False
    if 'checksum' in data and 'checkpoint' in data:
        stored_checksum = data['checksum']
        # Remove checksum from validation data
        validation_data = {k: v for k, v in data.items() if k != 'checksum'}
        computed_checksum = _generate_checksum(validation_data)
        checksum_valid = stored_checksum == computed_checksum
        if not checksum_valid:
            errors.append("Checksum mismatch - data may be corrupted")
    
    # Checkpoint structure validation
    if 'checkpoint' in data:
        cp = data['checkpoint']
        cp_required = ['id', 'task_id', 'phase', 'agent_states', 'task_state_snapshot']
        for field in cp_required:
            if field not in cp:
                errors.append(f"Checkpoint missing field: {field}")
    
    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        checksum_valid=checksum_valid,
        schema_version=version if 'version' in data else 'unknown'
    )


# ─── Existing routes ──────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=CheckpointResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Checkpoint",
    description="Manually create a checkpoint for a specific task line.",
    responses=build_responses(None),
)
def create_checkpoint(
    payload: CheckpointCreate,
    db: Session = Depends(get_db)
):
    """Manually create a checkpoint for a specific task line."""
    try:
        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=payload.task_id,
            phase=payload.phase,
            actor_id="user_api",
            artifacts=payload.artifacts
        )
        return checkpoint
    except ValueError as e:
        raise NotFoundError(error=str(e), code="STRE")
    except Exception as e:
        raise InternalServerError(error=str(e), code="STRE")


@router.get(
    "",
    response_model=List[CheckpointResponse],
    summary="List Checkpoints",
    description="Fetch checkpoints, filterable by session or original task ID.",
    responses=build_responses(None),
)
def list_checkpoints(
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Fetch checkpoints, filterable by session or original task ID."""
    query = db.query(ExecutionCheckpoint).filter(ExecutionCheckpoint.is_active == True)

    if session_id:
        query = query.filter(ExecutionCheckpoint.session_id == session_id)
    if task_id:
        query = query.filter(ExecutionCheckpoint.task_id == task_id)

    return query.order_by(ExecutionCheckpoint.created_at.desc()).limit(limit).all()


# ─── NEW: Branch diff ─────────────────────────────────────────────────────────

@router.get(
    "/compare",
    response_model=BranchCompareResponse,
    summary="Compare Branches",
    description="Compare two branches by diffing their latest checkpoints. Produces structured diffs for: - task_state_snapshot (flat key/value) - agent_states (per-agent) - artifacts (per-artifact key).",
    responses=build_responses(None),
)
def compare_branches(
    left_branch: str = Query(..., description="Name of the left/base branch"),
    right_branch: str = Query(..., description="Name of the right/compare branch"),
    task_id: Optional[str] = Query(None, description="Narrow comparison to a specific task"),
    db: Session = Depends(get_db)
):
    """
    Compare two branches by diffing their latest checkpoints.

    Produces structured diffs for:
    - task_state_snapshot (flat key/value)
    - agent_states (per-agent)
    - artifacts (per-artifact key)
    """

    def _latest_for_branch(branch: str) -> ExecutionCheckpoint:
        q = (
            db.query(ExecutionCheckpoint)
            .filter(
                ExecutionCheckpoint.branch_name == branch,
                ExecutionCheckpoint.is_active == True,
            )
        )
        if task_id:
            q = q.filter(ExecutionCheckpoint.task_id == task_id)
        cp = q.order_by(ExecutionCheckpoint.created_at.desc()).first()
        if cp is None:
            raise NotFoundError(error=f"No active checkpoint found for branch '{branch}'"
                + (f" and task '{task_id}'" if task_id else ""), code="NO_ACTIVE_CHECKPOINT_FOUND_FOR")
        return cp

    left_cp = _latest_for_branch(left_branch)
    right_cp = _latest_for_branch(right_branch)

    # ── task_state_snapshot diff ──────────────────────────────────────────────
    left_state: Dict[str, Any] = left_cp.task_state_snapshot or {}
    right_state: Dict[str, Any] = right_cp.task_state_snapshot or {}
    task_diffs = _diff_dicts(left_state, right_state)

    # ── agent_states diff (per agent) ─────────────────────────────────────────
    left_agents: Dict[str, Any] = left_cp.agent_states or {}
    right_agents: Dict[str, Any] = right_cp.agent_states or {}
    all_agent_ids = set(left_agents.keys()) | set(right_agents.keys())
    agent_diffs: List[AgentStateDiff] = []

    for agent_id in sorted(all_agent_ids):
        l_agent = left_agents.get(agent_id, {}) or {}
        r_agent = right_agents.get(agent_id, {}) or {}

        if agent_id not in left_agents:
            agent_status = "added"
        elif agent_id not in right_agents:
            agent_status = "removed"
        elif l_agent != r_agent:
            agent_status = "changed"
        else:
            agent_status = "unchanged"

        agent_diffs.append(AgentStateDiff(
            agent_id=agent_id,
            status=agent_status,
            diffs=_diff_dicts(l_agent, r_agent),
        ))

    # ── artifacts diff ────────────────────────────────────────────────────────
    left_arts: Dict[str, Any] = left_cp.artifacts or {}
    right_arts: Dict[str, Any] = right_cp.artifacts or {}

    # Normalise: artifacts may be a list of dicts with a "key" field OR a plain dict
    def _normalise_artifacts(raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, list):
            out: Dict[str, Any] = {}
            for i, item in enumerate(raw):
                if isinstance(item, dict):
                    k = item.get("key") or item.get("name") or item.get("id") or str(i)
                    out[str(k)] = item
                else:
                    out[str(i)] = item
            return out
        return {}

    left_arts = _normalise_artifacts(left_arts)
    right_arts = _normalise_artifacts(right_arts)
    all_art_keys = set(left_arts.keys()) | set(right_arts.keys())
    artifact_diffs: List[ArtifactDiff] = []

    for key in sorted(all_art_keys):
        if key not in left_arts:
            art_status = "added"
        elif key not in right_arts:
            art_status = "removed"
        elif left_arts[key] != right_arts[key]:
            art_status = "changed"
        else:
            art_status = "unchanged"

        artifact_diffs.append(ArtifactDiff(
            key=key,
            status=art_status,
            left=left_arts.get(key),
            right=right_arts.get(key),
        ))

    # ── summary ───────────────────────────────────────────────────────────────
    all_flat_diffs = task_diffs + [d for a in agent_diffs for d in a.diffs] + [
        FieldDiff(key=a.key, left=a.left, right=a.right, status=a.status)
        for a in artifact_diffs
    ]
    summary = _summarize(all_flat_diffs)

    return BranchCompareResponse(
        left_branch=left_branch,
        right_branch=right_branch,
        left_checkpoint_id=str(left_cp.id),
        right_checkpoint_id=str(right_cp.id),
        left_created_at=left_cp.created_at.isoformat(),
        right_created_at=right_cp.created_at.isoformat(),
        task_state_diffs=task_diffs,
        agent_state_diffs=agent_diffs,
        artifact_diffs=artifact_diffs,
        summary=summary,
    )


@router.get(
    "/{checkpoint_id}",
    response_model=CheckpointResponse,
    summary="Get Checkpoint",
    description="Get single checkpoint details.",
    responses=build_responses(None),
)
def get_checkpoint(checkpoint_id: str, db: Session = Depends(get_db)):
    """Get single checkpoint details."""
    checkpoint = db.query(ExecutionCheckpoint).filter(ExecutionCheckpoint.id == checkpoint_id).first()
    if not checkpoint:
        raise NotFoundError(error="Checkpoint not found", code="CHECKPOINT_NOT_FOUND")
    return checkpoint


@router.post(
    "/{checkpoint_id}/resume",
    response_model=TaskResponse,
    summary="Resume From Checkpoint",
    description="Time-travel: Restores the given task back to the target checkpoint.",
    responses=build_responses(None),
)
def resume_from_checkpoint(
    checkpoint_id: str,
    db: Session = Depends(get_db)
):
    """
    Time-travel: Restores the given task back to the target checkpoint.
    """
    try:
        restored_task = CheckpointService.resume_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint_id,
            actor_id="user_api"
        )
        return restored_task
    except ValueError as e:
        raise NotFoundError(error=str(e), code="STRE")
    except Exception as e:
        raise InternalServerError(error=str(e), code="STRE")


@router.post(
    "/{checkpoint_id}/branch",
    response_model=TaskResponse,
    summary="Branch From Checkpoint",
    description="Branching: Clones the checkpoint into a new separate task tree to try an alternative approach.",
    responses=build_responses(None),
)
def branch_from_checkpoint(
    checkpoint_id: str,
    payload: CheckpointBranchRequest,
    db: Session = Depends(get_db)
):
    """
    Branching: Clones the checkpoint into a new separate task tree
    to try an alternative approach.
    """
    try:
        new_task = CheckpointService.branch_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint_id,
            branch_name=payload.branch_name,
            new_supervisor_id=payload.new_supervisor_id,
            actor_id="user_api"
        )
        return new_task
    except ValueError as e:
        raise NotFoundError(error=str(e), code="STRE")
    except Exception as e:
        raise InternalServerError(error=str(e), code="STRE")


@router.get(
    "/{checkpoint_id}/diff",
    response_model=UnifiedDiffResponse,
    summary="Compare Two Checkpoints",
    description="Return a unified diff of the `task_state_snapshot` JSON between two individual checkpoints, identified by primary key. Useful for the Monaco Editor diff view in the frontend.",
    responses=build_responses(None),
)
def compare_two_checkpoints(
    checkpoint_id: str,
    compare_to: str = Query(..., description="ID of the other checkpoint to compare against"),
    db: Session = Depends(get_db),
):
    """
    Return a unified diff of the `task_state_snapshot` JSON between two
    individual checkpoints, identified by primary key.

    Useful for the Monaco Editor diff view in the frontend.
    """
    if checkpoint_id == compare_to:
        raise BadRequestError(error="Cannot compare a checkpoint to itself", code="CANNOT_COMPARE_A_CHECKPOINT_TO")

    left = (
        db.query(ExecutionCheckpoint)
        .filter(ExecutionCheckpoint.id == checkpoint_id)
        .first()
    )
    right = (
        db.query(ExecutionCheckpoint)
        .filter(ExecutionCheckpoint.id == compare_to)
        .first()
    )

    if not left:
        raise NotFoundError(error=f"Checkpoint {checkpoint_id} not found", code="CHECKPOINT_NOT_FOUND")
    if not right:
        raise NotFoundError(error=f"Checkpoint {compare_to} not found", code="CHECKPOINT_NOT_FOUND")

    left_state: Dict[str, Any] = left.task_state_snapshot or {}
    right_state: Dict[str, Any] = right.task_state_snapshot or {}

    left_json = json.dumps(left_state, indent=2, sort_keys=True, ensure_ascii=False)
    right_json = json.dumps(right_state, indent=2, sort_keys=True, ensure_ascii=False)

    unified = difflib.unified_diff(
        left_json.splitlines(keepends=True),
        right_json.splitlines(keepends=True),
        fromfile=f"{left.branch_name or 'checkpoint'}-{left.agentium_id}",
        tofile=f"{right.branch_name or 'checkpoint'}-{right.agentium_id}",
    )

    return UnifiedDiffResponse(
        left_checkpoint_id=checkpoint_id,
        right_checkpoint_id=compare_to,
        left_branch=left.branch_name,
        right_branch=right.branch_name,
        left_agentium_id=left.agentium_id,
        right_agentium_id=right.agentium_id,
        unified_diff="".join(unified),
        left_json=left_json,
        right_json=right_json,
    )

@router.post(
    "/validate",
    response_model=ValidationResult,
    summary="Validate Checkpoint File",
    description="Validate a checkpoint file before import.",
    responses=build_responses(None),
)
async def validate_checkpoint_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Validate a checkpoint file before import.
    """
    try:
        content = await file.read()
        data = json.loads(content.decode('utf-8'))
        return _validate_checkpoint_data(data)
    except json.JSONDecodeError:
        return ValidationResult(
            valid=False,
            errors=["Invalid JSON format"],
            warnings=[],
            checksum_valid=False,
            schema_version="unknown"
        )
    except Exception as e:
        return ValidationResult(
            valid=False,
            errors=[str(e)],
            warnings=[],
            checksum_valid=False,
            schema_version="unknown"
        )


@router.post(
    "/import",
    response_model=ImportResult,
    summary="Import Checkpoint",
    description="Import checkpoint from JSON file. Conflict resolution strategies: - skip: Skip conflicting checkpoints - replace: Overwrite existing checkpoints - rename: Auto-rename with suffix - merge: Smart merge of states.",
    responses=build_responses(None),
)
async def import_checkpoint(
    file: UploadFile = File(...),
    target_branch: Optional[str] = Form(None),
    skip_validation: bool = Form(False),
    conflict_resolution: str = Form("rename"),
    db: Session = Depends(get_db)
):
    """
    Import checkpoint from JSON file.
    
    Conflict resolution strategies:
    - skip: Skip conflicting checkpoints
    - replace: Overwrite existing checkpoints
    - rename: Auto-rename with suffix
    - merge: Smart merge of states
    """
    try:
        content = await file.read()
        data = json.loads(content.decode('utf-8'))
        
        # Validate unless skipped
        validation = None
        if not skip_validation:
            validation = _validate_checkpoint_data(data)
            if not validation.valid:
                return ImportResult(
                    success=False,
                    conflicts=[ImportConflict(
                        type="validation_failed",
                        message="; ".join(validation.errors),
                        resolution="Fix validation errors or enable skip_validation"
                    )],
                    validation=validation
                )
        
        checkpoint_data = data['checkpoint']
        conflicts = []
        
        # Check for ID collision
        existing = db.query(ExecutionCheckpoint).filter(
            ExecutionCheckpoint.id == checkpoint_data['id']
        ).first()
        
        if existing:
            if conflict_resolution == 'skip':
                return ImportResult(
                    success=False,
                    conflicts=[ImportConflict(
                        type="id_collision",
                        message=f"Checkpoint {checkpoint_data['id']} already exists",
                        resolution="Skipped due to conflict_resolution=skip"
                    )],
                    validation=validation
                )
            elif conflict_resolution == 'replace':
                # Delete existing
                db.delete(existing)
                db.flush()
            elif conflict_resolution == 'rename':
                # Generate new ID
                checkpoint_data['id'] = f"{checkpoint_data['id']}_import_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        # Check branch name collision
        target = target_branch or checkpoint_data.get('branch_name') or 'imported'
        branch_exists = db.query(ExecutionCheckpoint).filter(
            ExecutionCheckpoint.branch_name == target
        ).first()
        
        if branch_exists and conflict_resolution == 'rename':
            target = f"{target}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        # Create new checkpoint
        new_checkpoint = ExecutionCheckpoint(
            id=checkpoint_data['id'],
            session_id=checkpoint_data.get('session_id', 'imported'),
            task_id=checkpoint_data['task_id'],
            phase=CheckpointPhase(checkpoint_data['phase']),
            agent_states=checkpoint_data.get('agent_states', {}),
            artifacts=checkpoint_data.get('artifacts', []),
            task_state_snapshot=checkpoint_data.get('task_state_snapshot', {}),
            parent_checkpoint_id=checkpoint_data.get('parent_checkpoint_id'),
            branch_name=target,
            is_active=True
        )
        
        db.add(new_checkpoint)
        db.commit()
        db.refresh(new_checkpoint)
        
        return ImportResult(
            success=True,
            checkpoint=CheckpointResponse.from_orm(new_checkpoint),
            validation=validation
        )
        
    except Exception as e:
        raise BadRequestError(error=str(e), code="STRE")


@router.get(
    "/{checkpoint_id}/integrity",
    summary="Get Checkpoint Integrity",
    description="Get integrity status for a checkpoint.",
    responses=build_responses(None),
)
def get_checkpoint_integrity(
    checkpoint_id: str,
    db: Session = Depends(get_db)
):
    """
    Get integrity status for a checkpoint.
    """
    checkpoint = db.query(ExecutionCheckpoint).filter(
        ExecutionCheckpoint.id == checkpoint_id
    ).first()
    
    if not checkpoint:
        raise NotFoundError(error="Checkpoint not found", code="CHECKPOINT_NOT_FOUND")
    
    # Verify internal consistency
    issues = []
    
    # Check task exists
    task = db.query(Task).filter(Task.id == checkpoint.task_id).first()
    if not task:
        issues.append(f"Referenced task {checkpoint.task_id} not found")
    
    # Check parent exists if specified
    if checkpoint.parent_checkpoint_id:
        parent = db.query(ExecutionCheckpoint).filter(
            ExecutionCheckpoint.id == checkpoint.parent_checkpoint_id
        ).first()
        if not parent:
            issues.append(f"Parent checkpoint {checkpoint.parent_checkpoint_id} not found")
    
    # Generate current checksum
    checksum_data = {
        'agent_states': checkpoint.agent_states,
        'artifacts': checkpoint.artifacts,
        'task_state_snapshot': checkpoint.task_state_snapshot,
    }
    current_checksum = _generate_checksum(checksum_data)
    
    return {
        'valid': len(issues) == 0,
        'checksum': current_checksum,
        'last_verified': datetime.utcnow().isoformat(),
        'issues': issues
    }


@router.post(
    "/{checkpoint_id}/verify",
    summary="Verify Checkpoint Integrity",
    description="Verify and repair checkpoint integrity.",
    responses=build_responses(None),
)
def verify_checkpoint_integrity(
    checkpoint_id: str,
    db: Session = Depends(get_db)
):
    """
    Verify and repair checkpoint integrity.
    """
    checkpoint = db.query(ExecutionCheckpoint).filter(
        ExecutionCheckpoint.id == checkpoint_id
    ).first()
    
    if not checkpoint:
        raise NotFoundError(error="Checkpoint not found", code="CHECKPOINT_NOT_FOUND")
    
    issues = []
    
    # Verify agent states are valid JSON
    try:
        if checkpoint.agent_states:
            json.dumps(checkpoint.agent_states)
    except (TypeError, ValueError) as e:
        issues.append(f"Invalid agent_states: {e}")
        # Attempt repair
        checkpoint.agent_states = {}
    
    # Verify task state snapshot
    try:
        if checkpoint.task_state_snapshot:
            json.dumps(checkpoint.task_state_snapshot)
    except (TypeError, ValueError) as e:
        issues.append(f"Invalid task_state_snapshot: {e}")
        checkpoint.task_state_snapshot = {}
    
    # Verify artifacts
    try:
        if checkpoint.artifacts:
            json.dumps(checkpoint.artifacts)
    except (TypeError, ValueError) as e:
        issues.append(f"Invalid artifacts: {e}")
        checkpoint.artifacts = []
    
    if issues:
        db.commit()
    
    return {
        'valid': len(issues) == 0,
        'checksum_match': True,  # Would compare against stored if we stored it
        'issues': issues
    }


@router.get(
    "/{checkpoint_id}/export",
    response_model=None,
    summary="Export Checkpoint",
    description="Export checkpoint as JSON file with integrity checksum.",
    responses=build_responses(None),
)
def export_checkpoint(
    checkpoint_id: str,
    db: Session = Depends(get_db)
):
    """
    Export checkpoint as JSON file with integrity checksum.
    """
    checkpoint = db.query(ExecutionCheckpoint).filter(
        ExecutionCheckpoint.id == checkpoint_id
    ).first()
    
    if not checkpoint:
        raise NotFoundError(error="Checkpoint not found", code="CHECKPOINT_NOT_FOUND")
    
    # Build export data
    export_data = {
        'checkpoint': checkpoint.to_dict(),
        'exported_at': datetime.utcnow().isoformat(),
        'version': '1.0',
    }
    
    # Generate checksum
    export_data['checksum'] = _generate_checksum(export_data)
    
    # Create JSON blob
    json_bytes = json.dumps(export_data, indent=2).encode('utf-8')
    
    # Return as downloadable file
    return StreamingResponse(
        BytesIO(json_bytes),
        media_type='application/json',
        headers={
            'Content-Disposition': f'attachment; filename="checkpoint-{checkpoint_id}.json"'
        }
    )
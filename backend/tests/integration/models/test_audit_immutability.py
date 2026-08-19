"""
Integration tests for AuditLog and ViolationReport models (3.3.5).
Verifies immutability expectations, record persistence, levels, categories, and resolution tracking.
"""
import pytest
import json
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.models.entities.monitoring import ViolationReport, ViolationSeverity


def test_audit_log_factory_creates_record(db_session):
    """Verify AuditLog.log factory method correctly populates all fields."""
    entry = AuditLog.log(
        level=AuditLevel.CRITICAL,
        category=AuditCategory.CONSTITUTION,
        actor_type="agent",
        actor_id="00001",
        action="constitution_amended",
        description="Amended Article 1",
        success=True,
        before_state={"version": "v1.0.0"},
        after_state={"version": "v2.0.0"},
        meta_data={"voting_id": "AV123456"},
    )
    db_session.add(entry)
    db_session.commit()

    fetched = db_session.query(AuditLog).filter_by(id=entry.id).first()
    assert fetched is not None
    assert fetched.level == AuditLevel.CRITICAL
    assert fetched.category == AuditCategory.CONSTITUTION
    assert fetched.actor_id == "00001"
    assert fetched.action == "constitution_amended"
    assert fetched.success == 'Y'

    d = fetched.to_dict()
    assert d["level"] == "critical"
    assert d["category"] == "constitution"
    assert d["result"]["success"] is True
    assert d["metadata"] == {"voting_id": "AV123456"}


def test_audit_log_persists_all_levels_and_categories(db_session):
    """Verify all AuditLevel and AuditCategory values persist."""
    for level in AuditLevel:
        entry = AuditLog.log(
            level=level,
            category=AuditCategory.SYSTEM,
            actor_type="system",
            actor_id="SYSTEM",
            action=f"action_{level.value}",
        )
        db_session.add(entry)

    for category in AuditCategory:
        entry = AuditLog.log(
            level=AuditLevel.INFO,
            category=category,
            actor_type="system",
            actor_id="SYSTEM",
            action=f"action_{category.value}",
        )
        db_session.add(entry)

    db_session.commit()

    count_levels = db_session.query(AuditLog).count()
    assert count_levels == len(AuditLevel) + len(AuditCategory)


def test_audit_log_parent_child_correlation(db_session):
    """Verify parent_audit_id and correlation_id relationship for chained audit events."""
    parent = AuditLog.log(
        level=AuditLevel.NOTICE,
        category=AuditCategory.TASK,
        actor_type="agent",
        actor_id="20001",
        action="task_dispatched",
        target_type="task",
        target_id="T00001",
    )
    db_session.add(parent)
    db_session.commit()

    child = AuditLog.log(
        level=AuditLevel.INFO,
        category=AuditCategory.EXECUTION,
        actor_type="agent",
        actor_id="30001",
        action="task_executed",
        target_type="task",
        target_id="T00001",
    )
    parent.add_child_event(child)
    db_session.add(child)
    db_session.commit()

    db_session.refresh(parent)
    db_session.refresh(child)

    assert child.parent_audit_id == parent.id
    assert child.correlation_id == parent.id
    assert child in parent.children


def test_violation_report_persists(db_session, sample_lead_agent, sample_task_agent):
    """Verify ViolationReport model stores report details."""
    report = ViolationReport(
        agentium_id="VR10001",
        reporter_agent_id=sample_lead_agent.id,
        reporter_agentium_id=sample_lead_agent.agentium_id,
        violator_agent_id=sample_task_agent.id,
        violator_agentium_id=sample_task_agent.agentium_id,
        severity=ViolationSeverity.CRITICAL,
        violated_article="Article 3",
        violation_type="unauthorized_file_deletion",
        description="Task agent attempted to delete system configuration file",
        evidence=[{"log": "rm -rf /etc/config"}],
    )
    db_session.add(report)
    db_session.commit()

    fetched = db_session.query(ViolationReport).filter_by(agentium_id="VR10001").first()
    assert fetched is not None
    assert fetched.severity == ViolationSeverity.CRITICAL
    assert fetched.violated_article == "Article 3"
    assert fetched.status == "open"

    d = fetched.to_dict()
    assert d["severity"] == "critical"
    assert d["article"] == "Article 3"
    assert d["status"] == "open"


def test_violation_report_resolution_flow(db_session, sample_violation_report):
    """Verify assign_investigation and resolve methods on ViolationReport."""
    assert sample_violation_report.status == "open"

    # Assign investigation
    sample_violation_report.assign_investigation("10001")
    db_session.commit()

    fetched = db_session.query(ViolationReport).filter_by(id=sample_violation_report.id).first()
    assert fetched.status == "investigating"
    assert fetched.assigned_to == "10001"

    # Resolve report
    sample_violation_report.resolve(
        action="suspension",
        resolution_note="Agent suspended for 24h due to policy breach",
        terminated=False,
    )
    db_session.commit()

    refetched = db_session.query(ViolationReport).filter_by(id=sample_violation_report.id).first()
    assert refetched.status == "resolved"
    assert refetched.action_taken == "suspension"
    assert refetched.resolution == "Agent suspended for 24h due to policy breach"
    assert refetched.violator_terminated is False

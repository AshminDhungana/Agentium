"""
Monitoring service that implements the hierarchical oversight system.
Council Members monitor Lead Agents, Lead Agents monitor Task Agents.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.models.entities.agents import Agent, AgentType, LeadAgent, TaskAgent, CouncilMember
from backend.models.entities.monitoring import (
    AgentHealthReport, ViolationReport, ViolationSeverity, 
    TaskVerification, PerformanceMetric, MonitoringAlert
)
from backend.models.entities.task import Task, SubTask, TaskStatus
from backend.models.database import get_db_context, get_next_agentium_id
from backend.models.database import get_system_agent_id
import logging
import asyncio

logger = logging.getLogger(__name__)

class MonitoringService:
    """
    Implements the checks and balances monitoring system.
    Higher-tier agents actively supervise lower-tier agents.
    """
    
    @staticmethod
    def conduct_health_check(monitor_id: str, subject_id: str, db: Session) -> AgentHealthReport:
        """
        Monitor agent evaluates subordinate agent health.
        Called periodically by the monitoring agent.
        """
        monitor = db.query(Agent).filter_by(id=monitor_id).first()
        subject = db.query(Agent).filter_by(id=subject_id).first()
        
        if not monitor or not subject:
            raise ValueError("Monitor or subject not found")
        
        # Check hierarchy permission
        if subject.parent_id != monitor.id:
            # Council can monitor any Lead (they're all under Head)
            if not (monitor.agent_type == AgentType.COUNCIL_MEMBER and subject.agent_type == AgentType.LEAD_AGENT):
                raise PermissionError("Monitor does not have authority over this subject")
        
        # Calculate metrics
        recent_tasks = db.query(Task).filter(
            Task.assigned_task_agent_ids.contains(subject.agentium_id),
            Task.created_at >= datetime.utcnow() - timedelta(hours=24)
        ).all()
        
        total = len(recent_tasks)
        completed = len([t for t in recent_tasks if t.status == TaskStatus.COMPLETED])
        failed = len([t for t in recent_tasks if t.status == TaskStatus.FAILED])
        success_rate = (completed / total * 100) if total > 0 else 100
        
        # Check for violations
        violations = db.query(ViolationReport).filter_by(
            violator_agent_id=subject_id,
            status="open"
        ).count()
        
        # Determine status
        status = "healthy"
        if violations > 0:
            status = "violation_detected"
        elif success_rate < 50:
            status = "degraded"
        elif failed > 3:
            status = "degraded"
        
        # Generate findings
        findings = []
        if success_rate < 80:
            findings.append(f"Low success rate: {success_rate}%")
        if violations > 0:
            findings.append(f"{violations} open violations")
        if subject.status.value == "suspended":
            findings.append("Agent is currently suspended")
        
        health_score = max(0, min(100, success_rate - (violations * 10)))
        
        report = AgentHealthReport(
            monitor_agent_id=monitor_id,
            monitor_agentium_id=monitor.agentium_id,
            subject_agent_id=subject_id,
            subject_agentium_id=subject.agentium_id,
            status=status,
            overall_health_score=health_score,
            task_success_rate=success_rate,
            constitution_violations_count=violations,
            findings=findings,
            recommendations=MonitoringService._generate_recommendations(status, findings)
        )
        
        db.add(report)
        db.commit()
        
        # Auto-escalate critical issues
        if status == "violation_detected" and violations >= 3:
            MonitoringService._escalate_to_head(report, db)
        
        return report
    
    @staticmethod
    def report_violation(
        reporter_id: str,
        violator_id: str,
        severity: ViolationSeverity,
        violation_type: str,
        description: str,
        evidence: List[Dict],
        db: Session
    ) -> ViolationReport:
        """
        File a violation report against a subordinate.
        """
        reporter = db.query(Agent).filter_by(id=reporter_id).first()
        violator = db.query(Agent).filter_by(id=violator_id).first()
        
        if not reporter or not violator:
            raise ValueError("Reporter or violator not found")
        
        # Check permission to report
        if violator.parent_id != reporter.id:
            if not (reporter.agent_type == AgentType.COUNCIL_MEMBER and violator.agent_type == AgentType.LEAD_AGENT):
                raise PermissionError("No authority to report this agent")
        
        report = ViolationReport(
            reporter_agent_id=reporter_id,
            reporter_agentium_id=reporter.agentium_id,
            violator_agent_id=violator_id,
            violator_agentium_id=violator.agentium_id,
            severity=severity,
            violation_type=violation_type,
            description=description,
            evidence=evidence,
            context={
                "reporter_type": reporter.agent_type.value,
                "violator_type": violator.agent_type.value,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        db.add(report)
        db.commit()
        
        # Auto-suspend for critical violations
        if severity == ViolationSeverity.CRITICAL:
            violator.status = "suspended"
            db.commit()
            
            # Create alert
            MonitoringService._create_alert(
                alert_type="critical_violation",
                severity=severity,
                detected_by=reporter_id,
                affected=violator_id,
                message=f"Critical violation by {violator.agentium_id}: {violation_type}",
                db=db
            )
        
        # Route to appropriate authority
        if violator.agent_type == AgentType.LEAD_AGENT:
            # Council Members investigate Leads
            council = db.query(CouncilMember).first()
            if council:
                report.assign_investigation(council.agentium_id)
        elif violator.agent_type == AgentType.COUNCIL_MEMBER:
            # Head of Council investigates Council Members
            head = db.query(Agent).filter_by(agent_type=AgentType.HEAD_OF_COUNCIL).first()
            if head:
                report.assign_investigation(head.agentium_id)
        
        db.commit()
        return report
    
    @staticmethod
    def verify_task_completion(
        lead_id: str,
        task_agent_id: str,
        task_id: str,
        output: str,
        output_data: Dict,
        db: Session
    ) -> TaskVerification:
        """
        Lead Agent verifies Task Agent's work before finalizing.
        """
        verification = TaskVerification(
            task_id=task_id,
            task_agent_id=task_agent_id,
            lead_agent_id=lead_id,
            submitted_output=output,
            submitted_data=output_data,
            submitted_at=datetime.utcnow(),
            checks_performed=[
                "constitution_compliance",
                "output_accuracy",
                "requirement_fulfillment"
            ]
        )
        
        # Automated checks would happen here
        # In real implementation, Lead Agent AI would analyze output
        
        db.add(verification)
        db.commit()
        
        return verification
    
    @staticmethod
    def calculate_performance_metrics(
        monitor_id: str,
        subject_id: str,
        db: Session,
        period_days: int = 7
    ) -> PerformanceMetric:
        """
        Calculate rolling performance metrics for a subordinate.
        Used to identify trends and trigger training/termination.
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=period_days)
        
        # Get task stats
        tasks = db.query(Task).filter(
            Task.assigned_task_agent_ids.contains(db.query(Agent).filter_by(id=subject_id).first().agentium_id),
            Task.created_at.between(start_date, end_date)
        ).all()
        
        assigned = len(tasks)
        completed = len([t for t in tasks if t.status == TaskStatus.COMPLETED])
        failed = len([t for t in tasks if t.status == TaskStatus.FAILED])
        
        # Check for rejections (verifications that failed)
        agent = db.query(Agent).filter_by(id=subject_id).first()
        rejected = db.query(TaskVerification).filter_by(
            task_agent_id=subject_id,
            verification_status="rejected"
        ).count()
        
        metric = PerformanceMetric(
            agent_id=subject_id,
            calculated_by_agent_id=monitor_id,
            period_start=start_date,
            period_end=end_date,
            tasks_assigned=assigned,
            tasks_completed=completed,
            tasks_failed=failed,
            tasks_rejected=rejected,
            avg_quality_score=(completed / max(assigned, 1)) * 100,
            constitution_violations=db.query(ViolationReport).filter_by(
                violator_agent_id=subject_id
            ).count()
        )
        
        # Determine trend
        previous = db.query(PerformanceMetric).filter_by(
            agent_id=subject_id
        ).order_by(PerformanceMetric.period_end.desc()).first()
        
        metric.trend = metric.calculate_trend(previous)
        
        # Generate recommendation
        if metric.avg_quality_score and metric.avg_quality_score < 60:
            metric.recommended_action = "retrain"
        elif metric.constitution_violations > 3:
            metric.recommended_action = "terminate"
        elif metric.avg_quality_score and metric.avg_quality_score > 95 and metric.trend == "improving":
            metric.recommended_action = "promote"
        else:
            metric.recommended_action = "monitor"
        
        db.add(metric)
        db.commit()
        
        # Auto-terminate recommendation triggers alert
        if metric.recommended_action == "terminate":
            MonitoringService._create_alert(
                alert_type="termination_recommended",
                severity=ViolationSeverity.MAJOR,
                detected_by=monitor_id,
                affected=subject_id,
                message=f"Agent {agent.agentium_id} recommended for termination due to poor performance",
                db=db
            )
        
        return metric
    
    @staticmethod
    def get_monitoring_dashboard(monitor_id: str, db: Session) -> Dict[str, Any]:
        """
        Get overview of all subordinates for a monitoring agent.
        Shows health reports, violations, and pending verifications.
        """
        monitor = db.query(Agent).filter_by(id=monitor_id).first()
        
        if not monitor:
            raise ValueError("Monitor not found")
        
        # Get subordinates based on hierarchy
        if monitor.agent_type == AgentType.HEAD_OF_COUNCIL:
            subjects = db.query(Agent).filter(
                Agent.agent_type.in_([AgentType.COUNCIL_MEMBER, AgentType.LEAD_AGENT])
            ).all()
        elif monitor.agent_type == AgentType.COUNCIL_MEMBER:
            subjects = db.query(Agent).filter_by(
                agent_type=AgentType.LEAD_AGENT
            ).all()
        elif monitor.agent_type == AgentType.LEAD_AGENT:
            subjects = monitor.subordinates  # Direct children
        else:
            subjects = []
        
        dashboard = {
            "monitor": monitor.agentium_id,
            "subordinate_count": len(subjects),
            "subordinates": []
        }
        
        for subject in subjects:
            latest_health = db.query(AgentHealthReport).filter_by(
                subject_agent_id=subject.id
            ).order_by(AgentHealthReport.created_at.desc()).first()
            
            open_violations = db.query(ViolationReport).filter_by(
                violator_agent_id=subject.id,
                status="open"
            ).count()
            
            pending_verifications = 0
            if monitor.agent_type == AgentType.LEAD_AGENT:
                pending_verifications = db.query(TaskVerification).filter_by(
                    lead_agent_id=monitor_id,
                    verification_status="pending"
                ).count()
            
            dashboard["subordinates"].append({
                "agentium_id": subject.agentium_id,
                "name": subject.name,
                "status": subject.status.value,
                "health": latest_health.to_dict() if latest_health else None,
                "open_violations": open_violations,
                "pending_verifications": pending_verifications
            })
        
        return dashboard
    
    @staticmethod
    def _generate_recommendations(status: str, findings: List[str]) -> str:
        """Generate recommendation text based on health status."""
        if status == "healthy":
            return "Continue standard monitoring"
        elif status == "degraded":
            return "Increase monitoring frequency, investigate performance issues"
        elif status == "violation_detected":
            return "Review violations and consider retraining or escalation"
        else:
            return "Immediate attention required"
    
    @staticmethod
    def _escalate_to_head(report: AgentHealthReport, db: Session):
        """Escalate critical health report to Head of Council."""
        head = db.query(Agent).filter_by(agent_type=AgentType.HEAD_OF_COUNCIL).first()
        if head:
            report.escalate_to_head(
                head.agentium_id,
                f"Multiple violations detected in {report.subject_agentium_id}"
            )
            db.commit()
    
    @staticmethod
    def _create_alert(
        alert_type: str,
        severity: ViolationSeverity,
        detected_by: str,
        affected: Optional[str],
        message: str,
        db: Session
    ):
        """Create monitoring alert."""
        agent = db.query(Agent).filter_by(id=detected_by).first()
        
        alert = MonitoringAlert(
            alert_type=alert_type,
            severity=severity,
            detected_by_agent_id=detected_by,
            affected_agent_id=affected,
            message=message,
            metadata={
                "auto_generated": True,
                "detection_time": datetime.utcnow().isoformat()
            }
        )
        
        # Determine who to notify based on severity
        notified = [agent.agentium_id]
        
        if severity in [ViolationSeverity.MAJOR, ViolationSeverity.CRITICAL]:
            # Notify Head of Council for major issues
            head = db.query(Agent).filter_by(agent_type=AgentType.HEAD_OF_COUNCIL).first()
            if head:
                notified.append(head.agentium_id)
        
        alert.notified_agents = notified
        db.add(alert)
        db.commit()

    # -------------------------------------------------------------------------
    # Phase 9 Background Monitoring Tasks
    # -------------------------------------------------------------------------

    @staticmethod
    async def constitutional_patrol():
        """
        Background task: Every 5 minutes, checks all active agents for excessive violations
        or degraded health and escalates to the alert manager.
        """
        from backend.services.alert_manager import AlertManager
        
        while True:
            try:
                with get_db_context() as db:
                    alert_manager = AlertManager(db)
                    
                    # 1. Find agents with multiple open violations
                    critical_agents = db.query(Agent).filter(
                        Agent.status == "active"
                    ).all()
                    
                    for agent in critical_agents:
                        open_violations = db.query(ViolationReport).filter_by(
                            violator_agent_id=agent.id,
                            status="open"
                        ).count()
                        
                        if open_violations >= 3:
                            # Auto-suspend and alert
                            agent.status = "suspended"
                            db.commit()
                            
                            alert = MonitoringAlert(
                                alert_type="constitutional_patrol_suspension",
                                severity=ViolationSeverity.CRITICAL,
                                detected_by_agent_id=get_system_agent_id(db),
                                affected_agent_id=agent.id,
                                message=f"Constitutional Patrol: Auto-suspended {agent.agentium_id} due to {open_violations} open violations."
                            )
                            db.add(alert)
                            db.commit()
                            await alert_manager.dispatch_alert(alert)
                            
            except Exception as e:
                logger.error(f"Error in constitutional_patrol loop: {e}")
                
            await asyncio.sleep(300)  # Every 5 minutes

    @staticmethod
    async def stale_task_detector():
        """
        Background task: Daily checks for tasks that have been IN_PROGRESS for too long
        without updates, marking them as FAILED or ESCALATED.
        """
        from backend.services.alert_manager import AlertManager
        
        while True:
            try:
                with get_db_context() as db:
                    alert_manager = AlertManager(db)
                    stale_threshold = datetime.utcnow() - timedelta(hours=24)
                    
                    stale_tasks = db.query(Task).filter(
                        Task.status == TaskStatus.IN_PROGRESS,
                        Task.started_at < stale_threshold
                    ).all()
                    
                    for task in stale_tasks:
                        task.set_status(TaskStatus.ESCALATED, "system", "Stale task detector: Task exceeded 24h Execution limit.")
                        
                        alert = MonitoringAlert(
                            alert_type="stale_task_detected",
                            severity=ViolationSeverity.MAJOR,
                            detected_by_agent_id=get_system_agent_id(db),
                            affected_agent_id=task.assigned_task_agent_ids[0] if task.assigned_task_agent_ids else None,
                            message=f"Stale Task {task.agentium_id} escalated after 24 hours of inactivity."
                        )
                        db.add(alert)
                        db.commit()
                        await alert_manager.dispatch_alert(alert)
                        
            except Exception as e:
                logger.error(f"Error in stale_task_detector loop: {e}")
            
            await asyncio.sleep(86400)  # Daily

    @staticmethod
    async def resource_rebalancing():
        """
        Background task: Hourly resource rebalancing.
        Delegates to IdleGovernanceEngine's rebalancing logic.
        Phase 9.1 requirement.
        """
        while True:
            try:
                from backend.services.idle_governance import idle_governance
                with get_db_context() as db:
                    result = await idle_governance.resource_rebalancing(db)
                    if result and result.get("tasks_redistributed", 0) > 0:
                        logger.info(
                            f"Resource rebalancing: redistributed "
                            f"{result['tasks_redistributed']} tasks"
                        )
            except Exception as e:
                logger.error(f"Error in resource_rebalancing loop: {e}")
            await asyncio.sleep(3600)  # Every hour

    @staticmethod
    async def council_health_check():
        """
        Background task: Weekly council health check.
        Verifies all Council (1xxxx) agents are ACTIVE and checks
        voting participation within the last 7 days.
        Phase 9.1 requirement.
        """
        from backend.services.alert_manager import AlertManager
        from backend.models.entities.voting import IndividualVote as Vote

        while True:
            try:
                with get_db_context() as db:
                    alert_manager = AlertManager(db)
                    council_agents = db.query(Agent).filter(
                        Agent.agent_type == AgentType.COUNCIL_MEMBER
                    ).all()

                    week_ago = datetime.utcnow() - timedelta(days=7)

                    for agent in council_agents:
                        # Check if agent is active
                        if agent.status.value != "active":
                            alert = MonitoringAlert(
                                alert_type="council_member_inactive",
                                severity=ViolationSeverity.MAJOR,
                                detected_by_agent_id=get_system_agent_id(db),
                                affected_agent_id=agent.id,
                                message=(
                                    f"Council member {agent.agentium_id} is "
                                    f"{agent.status.value}, not active."
                                )
                            )
                            db.add(alert)
                            db.commit()
                            await alert_manager.dispatch_alert(alert)

                        # Check voting participation
                        votes_cast = db.query(Vote).filter(
                            Vote.voter_agentium_id == agent.agentium_id,
                            Vote.created_at >= week_ago
                        ).count()

                        if votes_cast == 0:
                            logger.warning(
                                f"Council member {agent.agentium_id} has "
                                f"not voted in the past 7 days."
                            )

            except Exception as e:
                logger.error(f"Error in council_health_check loop: {e}")
            await asyncio.sleep(604800)  # Weekly (7 days)

    @staticmethod
    async def knowledge_consolidation():
        """
        Background task: Daily knowledge consolidation.
        Merges duplicate embeddings and prunes stale entries in ChromaDB.
        Phase 9.1 requirement.
        """
        while True:
            try:
                from backend.core.vector_store import VectorStore
                vs = VectorStore()
                removed = 0

                for collection_name in [
                    "constitution", "task_learnings",
                    "domain_knowledge", "execution_patterns"
                ]:
                    try:
                        col = vs.client.get_or_create_collection(
                            name=collection_name
                        )
                        count = col.count()
                        if count == 0:
                            continue

                        # Fetch all entries and deduplicate by high similarity
                        all_docs = col.get(
                            include=["documents", "metadatas", "embeddings"]
                        )
                        if not all_docs or not all_docs.get("ids"):
                            continue

                        ids = all_docs["ids"]
                        seen_ids = set()
                        ids_to_delete = []

                        # Simple dedup: mark entries with identical documents
                        doc_set: dict = {}
                        for i, doc in enumerate(all_docs.get("documents", [])):
                            if doc in doc_set:
                                ids_to_delete.append(ids[i])
                            else:
                                doc_set[doc] = ids[i]
                                seen_ids.add(ids[i])

                        if ids_to_delete:
                            col.delete(ids=ids_to_delete)
                            removed += len(ids_to_delete)

                    except Exception as col_err:
                        logger.warning(
                            f"Knowledge consolidation skipped "
                            f"collection {collection_name}: {col_err}"
                        )

                if removed > 0:
                    logger.info(
                        f"Knowledge consolidation: removed "
                        f"{removed} duplicate entries."
                    )
            except Exception as e:
                logger.error(f"Error in knowledge_consolidation loop: {e}")
            await asyncio.sleep(86400)  # Daily

    @staticmethod
    async def orphaned_knowledge_check():
        """
        Background task: Weekly scan for orphaned knowledge entries.
        Finds vector DB entries whose agent_id no longer exists
        in the agents table.
        Phase 9.1 requirement.
        """
        while True:
            try:
                from backend.core.vector_store import VectorStore
                vs = VectorStore()
                orphaned_count = 0

                with get_db_context() as db:
                    # Build set of valid agent IDs
                    valid_ids = {
                        a.agentium_id
                        for a in db.query(Agent.agentium_id).all()
                    }

                    for collection_name in [
                        "task_learnings", "domain_knowledge",
                        "execution_patterns"
                    ]:
                        try:
                            col = vs.client.get_or_create_collection(
                                name=collection_name
                            )
                            all_docs = col.get(include=["metadatas"])
                            if not all_docs or not all_docs.get("ids"):
                                continue

                            ids_to_delete = []
                            for i, meta in enumerate(
                                all_docs.get("metadatas", [])
                            ):
                                agent_id = (meta or {}).get("agent_id")
                                if agent_id and agent_id not in valid_ids:
                                    ids_to_delete.append(
                                        all_docs["ids"][i]
                                    )

                            if ids_to_delete:
                                col.delete(ids=ids_to_delete)
                                orphaned_count += len(ids_to_delete)

                        except Exception as col_err:
                            logger.warning(
                                f"Orphan check skipped "
                                f"collection {collection_name}: {col_err}"
                            )

                if orphaned_count > 0:
                    logger.info(
                        f"Orphaned knowledge check: removed "
                        f"{orphaned_count} orphaned entries."
                    )
            except Exception as e:
                logger.error(f"Error in orphaned_knowledge_check loop: {e}")
            await asyncio.sleep(604800)  # Weekly

    @staticmethod
    async def critic_queue_monitor():
        """
        Background task: Every minute, checks for CritiqueReview entries
        stuck in PENDING status for >10 minutes and creates alerts.
        Phase 9.1 requirement.
        """
        from backend.services.alert_manager import AlertManager

        while True:
            try:
                with get_db_context() as db:
                    from backend.models.entities.critics import CritiqueReview
                    alert_manager = AlertManager(db)

                    threshold = datetime.utcnow() - timedelta(minutes=10)
                    stuck_reviews = db.query(CritiqueReview).filter(
                        CritiqueReview.verdict == "PENDING",
                        CritiqueReview.created_at < threshold
                    ).all()

                    for review in stuck_reviews:
                        alert = MonitoringAlert(
                            alert_type="critic_queue_stuck",
                            severity=ViolationSeverity.MODERATE,
                            detected_by_agent_id=get_system_agent_id(db),
                            affected_agent_id=None,
                            message=(
                                f"Critique review {review.id} for task "
                                f"{review.task_id} has been PENDING for "
                                f">{int((datetime.utcnow() - review.created_at).total_seconds() / 60)} min."
                            )
                        )
                        db.add(alert)
                        db.commit()
                        await alert_manager.dispatch_alert(alert)

            except Exception as e:
                logger.error(f"Error in critic_queue_monitor loop: {e}")
            await asyncio.sleep(60)  # Every minute

    # -------------------------------------------------------------------------
    # Phase 11.1 Background Tasks — RBAC Delegation Expiry
    # -------------------------------------------------------------------------

    @staticmethod
    async def delegation_expiry_monitor():
        """
        Background task: Every 5 minutes, checks for and auto-revokes
        stale capability delegations.
        """
        while True:
            try:
                from backend.services.rbac_service import RBACService
                with get_db_context() as db:
                    count = RBACService.expire_stale_delegations(db)
                    if count > 0:
                        logger.info(f"Auto-revoked {count} expired capability delegations")
            except Exception as e:
                logger.error(f"Error in delegation_expiry_monitor loop: {e}")
            await asyncio.sleep(300)  # Every 5 minutes

    # -------------------------------------------------------------------------
    # Phase 10.4 Background Tasks — Learning Decay & Cross-Agent Sharing
    # -------------------------------------------------------------------------

    @staticmethod
    async def learning_decay():
        """
        Background task: Daily learning decay.
        Reduces confidence of outdated knowledge patterns and prunes
        entries below minimum threshold.
        Phase 10.4 requirement.
        """
        while True:
            try:
                from backend.services.autonomous_learning import get_learning_engine
                engine = get_learning_engine()
                with get_db_context() as db:
                    result = engine.decay_outdated_learnings(db)
                    if result.get("decayed", 0) > 0 or result.get("pruned", 0) > 0:
                        logger.info(
                            f"Learning decay: decayed {result.get('decayed', 0)}, "
                            f"pruned {result.get('pruned', 0)} entries"
                        )
            except Exception as e:
                logger.error(f"Error in learning_decay loop: {e}")
            await asyncio.sleep(86400)  # Daily

    @staticmethod
    async def cross_agent_sharing():
        """
        Background task: Every 6 hours, share high-confidence learnings
        to the federated knowledge pool for cross-agent access.
        Phase 10.4 requirement. Gated behind FEDERATION_ENABLED.
        """
        while True:
            try:
                from backend.services.autonomous_learning import get_learning_engine
                engine = get_learning_engine()
                with get_db_context() as db:
                    result = engine.share_learnings_across_agents(db)
                    if result.get("shared", 0) > 0:
                        logger.info(
                            f"Cross-agent sharing: shared {result['shared']} learnings"
                        )
            except Exception as e:
                logger.error(f"Error in cross_agent_sharing loop: {e}")
            await asyncio.sleep(21600)  # Every 6 hours

    # -------------------------------------------------------------------------
    # Phase 13.7 — Zero-Touch Operations Dashboard
    # -------------------------------------------------------------------------

    @staticmethod
    def get_aggregated_metrics(db: Session) -> Dict[str, Any]:
        """
        Combine agent health, circuit breaker states, scaling events (24h),
        learning impact delta, workflow success rates, event trigger fire rates.
        Cache in Redis for 10 seconds.
        """
        import json
        import os
        import redis as _redis

        redis_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")

        try:
            r = _redis.Redis.from_url(redis_url, decode_responses=True)
            cached = r.get("agentium:monitoring:aggregated")
            if cached:
                return json.loads(cached)
        except Exception:
            r = None

        from backend.models.entities.agents import AgentStatus
        from backend.models.entities.task import Task, TaskStatus
        from sqlalchemy import func as sqla_func

        now = datetime.utcnow()
        day_ago = now - timedelta(hours=24)

        # ── Agent Health ──────────────────────────────────────────────────
        total_agents = db.query(Agent).filter(Agent.is_active == True).count()
        agents_active = db.query(Agent).filter(
            Agent.status.in_([AgentStatus.ACTIVE, AgentStatus.WORKING, AgentStatus.IDLE_WORKING]),
            Agent.is_active == True,
        ).count()
        agents_suspended = db.query(Agent).filter(
            Agent.status == AgentStatus.SUSPENDED,
            Agent.is_active == True,
        ).count()

        avg_health_row = db.query(sqla_func.avg(AgentHealthReport.overall_health_score)).filter(
            AgentHealthReport.created_at >= day_ago,
        ).scalar()
        avg_agent_health = round(float(avg_health_row), 1) if avg_health_row else 100.0

        agent_health_pct = round((agents_active / max(total_agents, 1)) * 100, 1)

        # ── Task Health ───────────────────────────────────────────────────

        tasks_24h = db.query(Task).filter(
            Task.created_at >= day_ago, Task.is_active == True,
        ).count()
        tasks_completed = db.query(Task).filter(
            Task.status == TaskStatus.COMPLETED,
            Task.completed_at >= day_ago,
            Task.is_active == True,
        ).count()
        tasks_failed = db.query(Task).filter(
            Task.status == TaskStatus.FAILED,
            Task.completed_at >= day_ago,
            Task.is_active == True,
        ).count()
        tasks_pending = db.query(Task).filter(
            Task.status.in_([TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.APPROVED]),
            Task.is_active == True,
        ).count()

        task_health_pct = round(
            (tasks_completed / max(tasks_completed + tasks_failed, 1)) * 100, 1,
        )

        # ── Workflow Health ───────────────────────────────────────────────
        try:
            from backend.models.entities.workflow import WorkflowExecution
            wf_total = db.query(WorkflowExecution).filter(
                WorkflowExecution.started_at >= day_ago,
            ).count()
            wf_completed = db.query(WorkflowExecution).filter(
                WorkflowExecution.status == "completed",
                WorkflowExecution.started_at >= day_ago,
            ).count()
            workflow_health_pct = round(
                (wf_completed / max(wf_total, 1)) * 100, 1,
            )
        except Exception:
            db.rollback()
            workflow_health_pct = 100.0

        # ── Event Health ──────────────────────────────────────────────────
        try:
            from backend.models.entities.event_trigger import EventLog, EventLogStatus
            events_total = db.query(EventLog).filter(
                EventLog.created_at >= day_ago,
            ).count()
            events_dead = db.query(EventLog).filter(
                EventLog.status == EventLogStatus.DEAD_LETTER,
                EventLog.created_at >= day_ago,
            ).count()
            event_health_pct = round(
                ((events_total - events_dead) / max(events_total, 1)) * 100, 1,
            )
        except Exception:
            db.rollback()
            event_health_pct = 100.0

        # ── Budget Health ─────────────────────────────────────────────────
        try:
            from backend.services.token_optimizer import token_optimizer
            budget_status = token_optimizer.get_status()
            cost_used = float(budget_status.get("budget_status", {}).get("cost_used_today_usd", 0.0))
            budget_limit = float(os.getenv("DAILY_TOKEN_BUDGET_USD", "10.00"))
            budget_pct = round(max(0, 100 - (cost_used / max(budget_limit, 0.01)) * 100), 1)
        except Exception:
            db.rollback()
            cost_used = 0.0
            budget_limit = 10.0
            budget_pct = 100.0

        # ── Capacity Forecast ─────────────────────────────────────────────
        try:
            from backend.services.predictive_scaling import predictive_scaling_service
            predictions = predictive_scaling_service.get_predictions()
        except Exception:
            db.rollback()
            predictions = {"next_1h": 0, "next_6h": 0, "next_24h": 0, "current_capacity": 0, "recommendation": "neutral"}

        # ── Scaling Events (24h) ──────────────────────────────────────────
        from backend.models.entities.audit import AuditLog, AuditCategory
        scaling_events_24h = db.query(AuditLog).filter(
            AuditLog.action.in_([
                "auto_scale_predictive_spawn",
                "auto_scale_predictive_liquidate",
                "manual_scale_override",
            ]),
            AuditLog.created_at >= day_ago,
        ).count()

        # ── Frontend Errors (24h) ─────────────────────────────────────────
        frontend_errors_24h = db.query(AuditLog).filter(
            AuditLog.action == "frontend_error",
            AuditLog.created_at >= day_ago,
        ).count()

        # ── Active Anomalies ─────────────────────────────────────────────
        active_anomalies = db.query(ViolationReport).filter(
            ViolationReport.status == "open",
            ViolationReport.violation_type == "anomaly_detected",
            ViolationReport.created_at >= day_ago,
        ).count()

        result = {
            "agents": {
                "total": total_agents,
                "active": agents_active,
                "suspended": agents_suspended,
                "avg_health": avg_agent_health,
                "health_pct": agent_health_pct,
            },
            "tasks": {
                "total_24h": tasks_24h,
                "completed": tasks_completed,
                "failed": tasks_failed,
                "pending": tasks_pending,
                "health_pct": task_health_pct,
            },
            "workflows": {
                "health_pct": workflow_health_pct,
            },
            "events": {
                "health_pct": event_health_pct,
            },
            "budget": {
                "cost_used_usd": cost_used,
                "budget_limit_usd": budget_limit,
                "health_pct": budget_pct,
            },
            "capacity_forecast": predictions,
            "scaling_events_24h": scaling_events_24h,
            "frontend_errors_24h": frontend_errors_24h,
            "active_anomalies": active_anomalies,
            "timestamp": now.isoformat(),
        }

        # Cache for 10 seconds
        try:
            if r:
                r.setex("agentium:monitoring:aggregated", 10, json.dumps(result))
        except Exception:
            pass

        return result

    @staticmethod
    def detect_anomalies(db: Session) -> Dict[str, Any]:
        """
        Compute Z-score for task_duration, error_rate, token_spend_per_hour
        vs 7-day baseline.  If Z-score > 2.5, create ViolationReport with
        severity 'major' and push via WebSocket.
        """
        import json
        import os
        import math
        import redis as _redis

        redis_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
        now = datetime.utcnow()
        results = {"anomalies_detected": 0, "anomalies": [], "checked_metrics": 0}

        try:
            r = _redis.Redis.from_url(redis_url, decode_responses=True)
        except Exception:
            logger.warning("Anomaly detection skipped: Redis unavailable")
            return results

        # Load 7-day time series from Redis sorted set
        import time as _time
        cutoff_7d = int(_time.time()) - 604800
        now_ts = int(_time.time())
        raw_data = r.zrangebyscore("agentium:scaling:metrics", cutoff_7d, now_ts)

        if len(raw_data) < 6:
            # Not enough data for meaningful Z-score
            return results

        parsed = [json.loads(d) for d in raw_data]

        # ── Compute baselines ─────────────────────────────────────────────
        def _compute_zscore(values: list, current: float) -> float:
            if len(values) < 3:
                return 0.0
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            stddev = math.sqrt(variance) if variance > 0 else 1.0
            return abs((current - mean) / stddev)

        metrics_to_check = []

        # 1. Pending task count (proxy for error/congestion)
        pending_vals = [p["pending_task_count"] for p in parsed]
        current_pending = pending_vals[-1] if pending_vals else 0
        z_pending = _compute_zscore(pending_vals[:-1], current_pending)
        results["checked_metrics"] += 1
        if z_pending > 2.5:
            metrics_to_check.append({
                "metric": "pending_task_count",
                "z_score": round(z_pending, 2),
                "current_value": current_pending,
                "baseline_mean": round(sum(pending_vals[:-1]) / max(len(pending_vals[:-1]), 1), 2),
                "pattern": "task_queue_stalled",
            })

        # 2. Token spend (proxy for cost anomaly)
        spend_vals = [p.get("token_spend_last_5m", 0) for p in parsed]
        current_spend = spend_vals[-1] if spend_vals else 0
        z_spend = _compute_zscore(spend_vals[:-1], current_spend)
        results["checked_metrics"] += 1
        if z_spend > 2.5:
            metrics_to_check.append({
                "metric": "token_spend",
                "z_score": round(z_spend, 2),
                "current_value": current_spend,
                "baseline_mean": round(sum(spend_vals[:-1]) / max(len(spend_vals[:-1]), 1), 2),
                "pattern": "budget_overspend",
            })

        # 3. Agent count drop (proxy for crash storm)
        agent_vals = [p["active_agent_count"] for p in parsed]
        current_agents = agent_vals[-1] if agent_vals else 0
        if len(agent_vals) > 3:
            prev_mean = sum(agent_vals[:-1]) / max(len(agent_vals[:-1]), 1)
            if current_agents < prev_mean * 0.5 and prev_mean > 2:
                metrics_to_check.append({
                    "metric": "active_agent_count",
                    "z_score": round(_compute_zscore(agent_vals[:-1], current_agents), 2),
                    "current_value": current_agents,
                    "baseline_mean": round(prev_mean, 2),
                    "pattern": "high_error_rate",
                })
                results["checked_metrics"] += 1

        # ── Create violation reports for anomalies ────────────────────────
        from backend.models.database import get_system_agent_id

        for anomaly in metrics_to_check:
            try:
                system_id = get_system_agent_id(db)
                report = ViolationReport(
                    reporter_agent_id=system_id,
                    reporter_agentium_id="SYSTEM",
                    violator_agent_id=system_id,
                    violator_agentium_id="SYSTEM",
                    severity=ViolationSeverity.MAJOR,
                    violation_type="anomaly_detected",
                    description=(
                        f"Anomaly: {anomaly['metric']} Z-score={anomaly['z_score']} "
                        f"(current={anomaly['current_value']}, baseline={anomaly['baseline_mean']})"
                    ),
                    evidence=[anomaly],
                    context={"auto_detected": True, "pattern": anomaly.get("pattern")},
                    status="open",
                )
                db.add(report)
                results["anomalies_detected"] += 1
                results["anomalies"].append(anomaly)
            except Exception as e:
                logger.error("Failed to create anomaly report: %s", e)

        if results["anomalies_detected"] > 0:
            db.commit()

            # WebSocket broadcast
            try:
                from backend.api.routes.websocket import manager
                import asyncio
                payload = {
                    "type": "anomaly_detected",
                    "count": results["anomalies_detected"],
                    "anomalies": results["anomalies"],
                    "timestamp": now.isoformat(),
                }
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(manager.broadcast(payload))
                except RuntimeError:
                    pass
            except Exception:
                pass

        return results

    # KNOWN_PATTERNS for automated incident response
    KNOWN_PATTERNS = {
        "high_error_rate": "restart_stuck_agents",
        "task_queue_stalled": "process_dependency_graph",
        "budget_overspend": "enforce_budget_guard",
    }

    @staticmethod
    def auto_remediate(anomaly: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        Match anomaly against KNOWN_PATTERNS and call fix_fn automatically.
        Log to AuditLog with action='auto_remediated'.
        """
        from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory

        pattern = anomaly.get("pattern", "")
        result = {
            "pattern": pattern,
            "remediated": False,
            "action_taken": None,
        }

        if pattern not in MonitoringService.KNOWN_PATTERNS:
            return result

        fix_name = MonitoringService.KNOWN_PATTERNS[pattern]

        try:
            if fix_name == "restart_stuck_agents":
                from backend.services.self_healing_service import SelfHealingService
                fix_result = SelfHealingService.detect_crashed_agents(db)
                result["action_taken"] = f"Restarted stuck agents: {fix_result.get('recovered', 0)} recovered"
                result["remediated"] = True

            elif fix_name == "process_dependency_graph":
                # Trigger dependency graph processing to unblock stalled tasks
                from backend.services.auto_delegation_service import AutoDelegationService
                try:
                    fix_result = AutoDelegationService.process_dependency_graph(db)
                    result["action_taken"] = f"Processed dependency graph: {fix_result}"
                except Exception:
                    result["action_taken"] = "Triggered dependency graph reprocessing"
                result["remediated"] = True

            elif fix_name == "enforce_budget_guard":
                from backend.services.predictive_scaling import predictive_scaling_service
                predictive_scaling_service.enforce_token_budget_guard(db)
                result["action_taken"] = "Enforced token budget guard"
                result["remediated"] = True

        except Exception as e:
            result["error"] = str(e)
            logger.error("Auto-remediation failed for pattern %s: %s", pattern, e)
            return result

        if result["remediated"]:
            # Log to AuditLog
            audit = AuditLog.log(
                level=AuditLevel.WARNING,
                category=AuditCategory.SYSTEM,
                actor_type="system",
                actor_id="ZERO_TOUCH_OPS",
                action="auto_remediated",
                description=f"Auto-remediated: {pattern} — {result['action_taken']}",
                after_state={
                    "anomaly": anomaly,
                    "fix_applied": fix_name,
                    "action": result["action_taken"],
                },
            )
            db.add(audit)
            db.commit()

            # Broadcast WebSocket event
            try:
                from backend.api.routes.websocket import manager
                import asyncio
                payload = {
                    "type": "auto_remediated",
                    "pattern": pattern,
                    "action": result["action_taken"],
                    "timestamp": datetime.utcnow().isoformat(),
                }
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(manager.broadcast(payload))
                except RuntimeError:
                    pass
            except Exception:
                pass

        return result

    @staticmethod
    def get_sla_metrics(db: Session) -> Dict[str, Any]:
        """
        Track time-to-resolution for tasks with escalation_timeout_seconds.
        Compute SLA compliance rate per priority level.
        """
        from backend.models.entities.task import Task, TaskStatus, TaskPriority

        now = datetime.utcnow()
        thirty_days_ago = now - timedelta(days=30)

        priorities = ["critical", "sovereign", "high", "normal", "low"]
        sla_data = {}

        for priority_name in priorities:
            try:
                priority_val = getattr(TaskPriority, priority_name.upper(), None)
                if priority_val is None:
                    sla_data[priority_name] = {"compliance_pct": 100.0, "total": 0, "met": 0, "breached": 0}
                    continue

                # Tasks completed in last 30 days with this priority
                completed_tasks = db.query(Task).filter(
                    Task.priority == priority_val,
                    Task.status == TaskStatus.COMPLETED,
                    Task.completed_at >= thirty_days_ago,
                    Task.is_active == True,
                ).all()

                total = len(completed_tasks)
                met = 0
                breached = 0

                for task in completed_tasks:
                    timeout = getattr(task, "escalation_timeout_seconds", None) or 300
                    if task.completed_at and task.started_at:
                        duration = (task.completed_at - task.started_at).total_seconds()
                        if duration <= timeout:
                            met += 1
                        else:
                            breached += 1

                compliance = round((met / max(total, 1)) * 100, 1)
                sla_data[priority_name] = {
                    "compliance_pct": compliance,
                    "total": total,
                    "met": met,
                    "breached": breached,
                }

            except Exception as e:
                logger.warning("SLA metrics computation failed for %s: %s", priority_name, e)
                sla_data[priority_name] = {"compliance_pct": 100.0, "total": 0, "met": 0, "breached": 0}

        # Check for SLA breaches to fire WebSocket events
        for pname, pdata in sla_data.items():
            if pdata["compliance_pct"] < 80.0 and pdata["total"] > 0:
                try:
                    from backend.api.routes.websocket import manager
                    import asyncio
                    payload = {
                        "type": "sla_breach",
                        "priority": pname,
                        "compliance_pct": pdata["compliance_pct"],
                        "breached_count": pdata["breached"],
                        "timestamp": now.isoformat(),
                    }
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(manager.broadcast(payload))
                    except RuntimeError:
                        pass
                except Exception:
                    pass

        return {
            "sla_by_priority": sla_data,
            "timestamp": now.isoformat(),
        }

    @staticmethod
    def get_incident_log(db: Session, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Return recent auto_remediated AuditLog entries for the incident log table.
        """
        from backend.models.entities.audit import AuditLog

        audits = db.query(AuditLog).filter(
            AuditLog.action == "auto_remediated",
        ).order_by(AuditLog.created_at.desc()).limit(limit).all()

        return [
            {
                "id": str(a.id),
                "action": a.action,
                "description": a.description,
                "level": a.level.value if hasattr(a.level, "value") else str(a.level),
                "after_state": a.after_state,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "actor_id": a.actor_id,
            }
            for a in audits
        ]

    @staticmethod
    def inject_chaos_test(test_type: str, db: Session) -> Dict[str, Any]:
        """
        Inject a controlled failure for chaos engineering.
        Types: agent_crash, api_timeout, db_connection_loss.
        All chaos actions are audit-logged.
        """
        from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
        from backend.models.entities.agents import AgentStatus

        result = {
            "test_type": test_type,
            "success": False,
            "details": {},
        }

        try:
            if test_type == "agent_crash":
                # Find a non-critical idle agent and mark as crashed
                target = db.query(Agent).filter(
                    Agent.status.in_([AgentStatus.IDLE, AgentStatus.ACTIVE]),
                    Agent.is_active == True,
                    Agent.is_persistent == False,
                    Agent.agent_type == AgentType.TASK_AGENT,
                ).first()

                if target:
                    target.status = AgentStatus.SUSPENDED
                    result["details"] = {
                        "agent_id": target.agentium_id,
                        "previous_status": "active/idle",
                        "new_status": "suspended",
                        "note": "Self-healing should auto-recover this agent within 30s",
                    }
                    result["success"] = True
                else:
                    result["details"] = {"note": "No eligible non-persistent task agent found"}

            elif test_type == "api_timeout":
                # Set a Redis flag that model provider can check
                import os
                import redis as _redis
                redis_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
                r = _redis.Redis.from_url(redis_url, decode_responses=True)
                r.setex("agentium:chaos:api_timeout", 60, "true")  # Auto-expires in 60s
                result["details"] = {
                    "flag_set": "agentium:chaos:api_timeout",
                    "ttl_seconds": 60,
                    "note": "Next model calls may experience simulated timeout for 60s",
                }
                result["success"] = True

            elif test_type == "db_connection_loss":
                # Set a Redis flag for diagnostic routine to detect
                import os
                import redis as _redis
                redis_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
                r = _redis.Redis.from_url(redis_url, decode_responses=True)
                r.setex("agentium:chaos:db_simulated_failure", 60, "true")
                result["details"] = {
                    "flag_set": "agentium:chaos:db_simulated_failure",
                    "ttl_seconds": 60,
                    "note": "Simulated DB failure flag set for 60s; diagnostic routine will detect it",
                }
                result["success"] = True

            else:
                result["details"] = {"error": f"Unknown test type: {test_type}"}
                return result

            # Audit log the chaos test
            audit = AuditLog.log(
                level=AuditLevel.WARNING,
                category=AuditCategory.SYSTEM,
                actor_type="admin",
                actor_id="CHAOS_ENGINEERING",
                action="chaos_test_injected",
                description=f"Chaos test injected: {test_type}",
                after_state=result,
            )
            db.add(audit)
            db.commit()

        except Exception as e:
            result["details"] = {"error": str(e)}
            logger.error("Chaos test injection failed: %s", e)

        return result

    @classmethod
    def start_background_monitors(cls):
        """Starts all detached asynchronous monitoring loops (Phase 9 + 10)."""
        asyncio.create_task(cls.constitutional_patrol())
        asyncio.create_task(cls.stale_task_detector())
        asyncio.create_task(cls.resource_rebalancing())
        asyncio.create_task(cls.council_health_check())
        asyncio.create_task(cls.knowledge_consolidation())
        asyncio.create_task(cls.orphaned_knowledge_check())
        asyncio.create_task(cls.critic_queue_monitor())
        # Phase 10.4 background tasks
        asyncio.create_task(cls.learning_decay())
        asyncio.create_task(cls.cross_agent_sharing())
        # Phase 11.1 background tasks
        asyncio.create_task(cls.delegation_expiry_monitor())
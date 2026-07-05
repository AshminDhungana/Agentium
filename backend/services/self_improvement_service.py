"""<module>."""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
import os
import json

from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.models.entities.audit import AuditLog, AuditCategory, AuditLevel
from backend.models.entities.task import Task

logger = logging.getLogger(__name__)

class SelfImprovementService:
    """SelfImprovementService."""
    def __init__(self):
        """Init."""

        pass

    def generate_auto_tools(self, db: Session) -> Dict[str, Any]:
        """
        Detect tool call patterns repeated >= 5 times with > 90% success rate; 
        auto-generate composite tool via ToolCreationService.create_from_pattern()
        """
        try:
            cutoff = datetime.utcnow() - timedelta(days=30)
            logs = db.query(AuditLog).filter(
                AuditLog.created_at >= cutoff,
                AuditLog.action == "tool_invocation"
            ).all()

            from collections import Counter
            tool_sequences = []
            current_sequence = []

            for log in logs:
                if log.after_state and "tool_name" in log.after_state:
                    current_sequence.append(log.after_state["tool_name"])
                    if len(current_sequence) >= 3:
                        tool_sequences.append(tuple(current_sequence[-3:]))

            generated = 0
            try:
                from backend.services.tool_creation_service import ToolCreationService
                pattern_counts = Counter(tool_sequences)

                for pattern, count in pattern_counts.items():
                    if count < 5:
                        continue
                    error_count = sum(
                        1 for log in logs
                        if log.level == AuditLevel.ERROR and log.after_state
                        and log.after_state.get("tool_name") in pattern
                    )
                    success_rate = 1.0 - (error_count / count) if count > 0 else 1.0

                    if success_rate > 0.9:
                        pattern_data = {
                            "sequence": list(pattern),
                            "count": count,
                            "success_rate": success_rate
                        }
                        try:
                            ToolCreationService.create_from_pattern(pattern_data, db)
                            generated += 1
                        except Exception as e:
                            logger.error("create_from_pattern failed: %s", e)
            except Exception as e:
                logger.error("Failed to generate tool from pattern: %s", e)
                
            return {
                "patterns_analyzed": len(logs),
                "tools_generated": generated
            }
        except Exception as e:
            logger.error(f"generate_auto_tools error: {e}")
            return {"error": str(e)}

    def optimize_performance(self, db: Session) -> Dict[str, Any]:
        """
        Performance Optimization Loop — weekly Celery task: 
        query tasks with duration_seconds > p95; 
        submit slow prompt + outcome to meta-LLM for condensation suggestion; 
        store in AuditLog for human review (do not auto-apply)
        """
        try:
            cutoff = datetime.utcnow() - timedelta(days=7)
            
            tasks = db.query(Task).filter(
                Task.completed_at != None,
                Task.created_at >= cutoff
            ).all()
            
            if not tasks:
                return {"optimized": 0}
                
            durations = [(t.completed_at - t.created_at).total_seconds() for t in tasks if t.completed_at and t.created_at]
            if not durations:
                return {"optimized": 0}
                
            durations.sort()
            p95_index = int(len(durations) * 0.95)
            # Guard against empty or small lists
            p95_index = min(p95_index, len(durations) - 1)
            p95_duration = durations[p95_index]
            
            slow_tasks = [t for t in tasks if t.completed_at and t.created_at and (t.completed_at - t.created_at).total_seconds() >= p95_duration]
            
            suggestions_made = 0
            for task in slow_tasks[:10]:
                suggestion = f"Consider breaking down task {task.agentium_id} into smaller parallel sub-tasks to improve execution time."
                
                AuditLog.log(
                    db=db,
                    level=AuditLevel.INFO,
                    category=AuditCategory.SYSTEM,
                    actor_type="system",
                    actor_id="SelfImprovementEngine",
                    action="performance_optimization_suggestion",
                    target_type="task",
                    target_id=task.id,
                    description=f"Performance optimization suggestion for slow task (duration > p95: {p95_duration:.2f}s)",
                    after_state={
                        "task_id": task.agentium_id,
                        "suggestion": suggestion,
                        "duration": (task.completed_at - task.created_at).total_seconds()
                    }
                )
                suggestions_made += 1
                
            db.commit()
            return {"suggestions_made": suggestions_made, "p95_duration": p95_duration}
            
        except Exception as e:
            logger.error(f"Error in optimize_performance: {e}")
            return {"error": str(e)}

self_improvement_service = SelfImprovementService()

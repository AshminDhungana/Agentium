"""
Idle Task for User Preference Optimization.
Runs during system idle time to maintain preference health.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from backend.models.database import get_db_context
from backend.models.entities.user_preference import UserPreference, UserPreferenceHistory
from backend.services.user_preference_service import UserPreferenceService
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory

logger = logging.getLogger(__name__)


class PreferenceOptimizerIdleTask:
    """
    Idle task that optimizes user preferences.
    Runs when the system is idle to perform maintenance.
    """

    def __init__(self):
        """Init."""

        self.name = "preference_optimizer"
        self.description = "Optimize user preferences: deduplicate, archive old history, generate recommendations"
        self.category = "maintenance"
        self.estimated_duration_seconds = 60
        self.estimated_tokens = 500

    def should_run(self, idle_duration_minutes: int) -> bool:
        """Determine if optimization should run based on idle time."""
        # Run every 30 minutes of idle time
        return idle_duration_minutes >= 30

    def get_priority(self) -> int:
        """Priority: lower number = higher priority."""
        return 50  # Medium priority

    def execute(self) -> Dict[str, Any]:
        """
        Execute preference optimization.
        Returns results summary.
        """
        logger.info("🔄 Starting preference optimization idle task")

        with get_db_context() as db:
            service = UserPreferenceService(db)
            results = {
                "timestamp": datetime.utcnow().isoformat(),
                "optimization": {},
                "recommendations": [],
                "errors": []
            }

            try:
                # 1. Run optimization
                opt_results = service.optimize_preferences()
                # Ensure opt_results is a dict for JSON serialization — the service
                # may return a list, which cannot be stored directly in a JSON object field.
                results["optimization"] = opt_results if isinstance(opt_results, dict) else {"items": opt_results}

                # 2. Generate recommendations
                recommendations = service.get_optimization_recommendations()
                results["recommendations"] = [r for r in recommendations if r['type'] in ['conflict', 'high_churn']]

                # 3. Auto-resolve simple conflicts (system vs user with same value)
                conflicts_resolved = self._auto_resolve_conflicts(db, service)
                results["auto_resolved_conflicts"] = conflicts_resolved

                # 4. Archive very old history (> 1 year)
                archived = self._archive_old_history(db)
                results["history_archived"] = archived

                # Log completion - FIX: Remove 'db=' parameter, use correct 'meta_data' parameter name
                # Create audit log entry and add to session
                # FIX: Ensure after_state is always a plain dict; AuditLog JSON columns
                # expect a dict (not a list). Wrap results to guarantee this.
                safe_results = results if isinstance(results, dict) else {"data": results}
                audit = AuditLog.log(
                    level=AuditLevel.INFO,
                    category=AuditCategory.GOVERNANCE,
                    actor_type="system",
                    actor_id="IDLE_GOVERNANCE",
                    action="preference_optimization_completed",
                    description=f"Preference optimization completed: {opt_results}",
                    after_state=safe_results,
                    meta_data={"results": safe_results}  # FIXED: use meta_data not metadata
                )
                db.add(audit)  # FIXED: Explicitly add to session

                db.commit()

                logger.info(f"✅ Preference optimization completed: {results}")

            except Exception as e:
                logger.error(f"❌ Preference optimization failed: {e}")
                results["errors"].append(str(e))
                db.rollback()

        return results

    def _auto_resolve_conflicts(self, db, service: UserPreferenceService) -> int:
        """
        Auto-resolve conflicts where system and user values are now identical.
        Remove the duplicate user preference.
        """
        conflicts = service.get_optimization_recommendations()
        resolved = 0

        for rec in conflicts:
            if rec['type'] == 'conflict':
                # Check if values are actually the same
                if rec.get('system_value') == rec.get('user_value'):
                    # Delete the user override (it's redundant)
                    pref = service.get_preference(rec['key'])
                    if pref and pref.user_id is not None:
                        pref.deactivate()
                        resolved += 1

        return resolved

    def _archive_old_history(self, db) -> int:
        """Archive history entries older than 1 year."""
        cutoff = datetime.utcnow() - timedelta(days=365)

        old_entries = db.query(UserPreferenceHistory).filter(
            UserPreferenceHistory.created_at < cutoff,
            UserPreferenceHistory.is_active == True
        ).all()

        archived = 0
        for entry in old_entries:
            entry.is_active = False
            archived += 1

        return archived

    def get_status(self) -> Dict[str, Any]:
        """Get current optimization status."""
        with get_db_context() as db:
            # Count active preferences
            total_prefs = db.query(UserPreference).filter(
                UserPreference.is_active == True
            ).count()

            # Count history entries
            total_history = db.query(UserPreferenceHistory).filter(
                UserPreferenceHistory.is_active == True
            ).count()

            # Find preferences with high churn
            from sqlalchemy import func
            high_churn = db.query(
                UserPreferenceHistory.preference_id,
                func.count('*').label('change_count')
            ).group_by(
                UserPreferenceHistory.preference_id
            ).having(func.count('*') > 10).count()

            return {
                "total_active_preferences": total_prefs,
                "total_history_entries": total_history,
                "high_churn_preferences": high_churn,
                "health_score": self._calculate_health_score(total_prefs, total_history, high_churn)
            }

    def _calculate_health_score(self, prefs: int, history: int, high_churn: int) -> float:
        """Calculate preference system health score (0-100)."""
        if prefs == 0:
            return 100.0

        # Penalize high history-to-preference ratio
        history_ratio = history / prefs if prefs > 0 else 0
        history_penalty = min(30, history_ratio * 5)  # Cap at 30 points

        # Penalize high churn
        churn_ratio = high_churn / prefs if prefs > 0 else 0
        churn_penalty = min(40, churn_ratio * 100)  # Cap at 40 points

        score = 100 - history_penalty - churn_penalty
        return max(0.0, round(score, 2))


# Singleton instance
preference_optimizer_task = PreferenceOptimizerIdleTask()
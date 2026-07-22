"""
User Preference Service for Agentium.
Manages CRUD operations, validation, optimization, and agent access control.
"""

import json
import uuid
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from backend.models.entities.user_preference import UserPreference, UserPreferenceHistory, PreferenceCategory
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory


class UserPreferenceService:
    """
    Service for managing user preferences with agent integration.
    """

    # Default preferences for new users
    DEFAULT_PREFERENCES = {
        'ui.theme': 'dark',
        'ui.language': 'en',
        'ui.sidebar_collapsed': False,
        'ui.font_size': 'medium',
        'chat.history_limit': 50,
        'chat.context_window_size': 10,
        'chat.auto_save': True,
        'chat.show_typing_indicator': True,
        'chat.prune_enabled': True,
        'chat.prune_inactivity_days': 7,
        'chat.prune_hard_delete_days': 30,
        'chat.prune_retain_count': 10,
        'chat.prune_schedule_cron': '0 3 * * *',
        'notifications.enabled': True,
        'notifications.sound': True,
        'notifications.channels': ['websocket', 'email'],
        'agents.default_timeout': 300,
        'agents.max_concurrent_tasks': 5,
        'agents.idle_timeout_minutes': 30,
        'tasks.auto_archive_days': 30,
        'tasks.default_priority': 'normal',
        'models.default_temperature': 0.7,
        'models.default_max_tokens': 4000,
        'privacy.share_usage_analytics': False,
        'tools.max_execution_time': 60,
        'tools.auto_retry_failed': True,
    }

    def __init__(self, db: Session):
        """Init."""

        self.db = db

    # ═══════════════════════════════════════════════════════════
    # CRUD Operations
    # ═══════════════════════════════════════════════════════════

    def get_preference(
        self,
        key: str,
        user_id: Optional[str] = None,
        scope: str = "global",
        scope_target_id: Optional[str] = None,
        default: Any = None
    ) -> Optional[UserPreference]:
        """Get a specific preference."""
        query = self.db.query(UserPreference).filter(
            UserPreference.key == key,
            UserPreference.is_active == True
        )

        if user_id:
            query = query.filter(
                or_(
                    UserPreference.user_id == user_id,
                    UserPreference.user_id.is_(None)  # System defaults
                )
            )
        else:
            query = query.filter(UserPreference.user_id.is_(None))

        query = query.filter(UserPreference.scope == scope)

        if scope_target_id:
            query = query.filter(UserPreference.scope_target_id == scope_target_id)

        # Order by user-specific first, then system
        pref = query.order_by(UserPreference.user_id.desc().nullslast()).first()

        return pref

    def get_value(
        self,
        key: str,
        user_id: Optional[str] = None,
        scope: str = "global",
        scope_target_id: Optional[str] = None,
        default: Any = None
    ) -> Any:
        """Get preference value directly."""
        pref = self.get_preference(key, user_id, scope, scope_target_id)
        if pref:
            return pref.get_value()
        return default

    def set_preference(
        self,
        key: str,
        value: Any,
        user_id: Optional[str] = None,
        category: str = PreferenceCategory.GENERAL,
        scope: str = "global",
        scope_target_id: Optional[str] = None,
        description: Optional[str] = None,
        editable_by_agents: bool = True,
        modified_by_agent: Optional[str] = None,
        change_reason: Optional[str] = None
    ) -> UserPreference:
        """Set a preference value."""
        # Detect data type
        data_type = self._detect_data_type(value)

        # Check if preference exists
        existing = self.get_preference(key, user_id, scope, scope_target_id)

        if existing:
            # Log change to history
            self._log_change(
                existing,
                existing.get_value(),
                value,
                modified_by_agent,
                change_reason or "manual_update"
            )

            # Update existing
            existing.set_value(value, modified_by_agent)
            existing.data_type = data_type
            existing.is_editable_by_agents = "Y" if editable_by_agents else "N"
            if description:
                existing.description = description

            self.db.commit()
            self.db.refresh(existing)
            return existing

        # Create new preference
        new_pref = UserPreference(
            id=str(uuid.uuid4()),
            agentium_id=self._generate_agentium_id(),
            user_id=user_id,
            category=category,
            key=key,
            value_json=json.dumps(value),
            data_type=data_type,
            scope=scope,
            scope_target_id=scope_target_id,
            description=description,
            is_editable_by_agents="Y" if editable_by_agents else "N",
            last_modified_by_agent=modified_by_agent,
            last_agent_modified_at=datetime.utcnow() if modified_by_agent else None,
        )

        self.db.add(new_pref)
        self.db.commit()
        self.db.refresh(new_pref)

        # Log creation
        self._log_change(new_pref, None, value, modified_by_agent, change_reason or "created")

        return new_pref

    def delete_preference(
        self,
        key: str,
        user_id: Optional[str] = None,
        scope: str = "global",
        scope_target_id: Optional[str] = None,
        deleted_by_agent: Optional[str] = None
    ) -> bool:
        """Soft-delete a preference."""
        pref = self.get_preference(key, user_id, scope, scope_target_id)

        if not pref:
            return False

        # Log deletion
        self._log_change(
            pref,
            pref.get_value(),
            None,
            deleted_by_agent,
            "deleted"
        )

        pref.deactivate()
        self.db.commit()
        return True

    # ═══════════════════════════════════════════════════════════
    # Bulk Operations
    # ═══════════════════════════════════════════════════════════

    def get_all_preferences(
        self,
        user_id: Optional[str] = None,
        category: Optional[str] = None,
        scope: Optional[str] = None,
        include_system: bool = True
    ) -> List[UserPreference]:
        """Get all preferences for a user."""
        query = self.db.query(UserPreference).filter(UserPreference.is_active == True)

        if user_id:
            if include_system:
                query = query.filter(
                    or_(
                        UserPreference.user_id == user_id,
                        UserPreference.user_id.is_(None)
                    )
                )
            else:
                query = query.filter(UserPreference.user_id == user_id)
        else:
            query = query.filter(UserPreference.user_id.is_(None))

        if category:
            query = query.filter(UserPreference.category == category)

        if scope:
            query = query.filter(UserPreference.scope == scope)

        return query.all()

    def get_preferences_dict(
        self,
        user_id: Optional[str] = None,
        category: Optional[str] = None,
        scope: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get all preferences as a nested dictionary."""
        prefs = self.get_all_preferences(user_id, category, scope)

        result = {}
        for pref in prefs:
            # User preferences override system defaults
            if pref.key in result and pref.user_id is None:
                continue  # Skip system default if user preference exists
            result[pref.key] = pref.get_value()

        return result

    def initialize_user_defaults(self, user_id: str) -> List[UserPreference]:
        """Initialize default preferences for a new user."""
        created = []

        for key, value in self.DEFAULT_PREFERENCES.items():
            # Determine category from key
            category = key.split('.')[0] if '.' in key else PreferenceCategory.GENERAL

            pref = self.set_preference(
                key=key,
                value=value,
                user_id=user_id,
                category=category,
                description=f"Default preference for {key}"
            )
            created.append(pref)

        return created

    # ═══════════════════════════════════════════════════════════
    # Agent Access Control
    # ═══════════════════════════════════════════════════════════

    def get_agent_accessible_preferences(
        self,
        agent_tier: str,
        agent_id: str,
        user_id: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[UserPreference]:
        """Get preferences that an agent is allowed to access."""
        query = self.db.query(UserPreference).filter(
            UserPreference.is_active == True,
            UserPreference.is_editable_by_agents == "Y"
        )

        if user_id:
            query = query.filter(
                or_(
                    UserPreference.user_id == user_id,
                    UserPreference.user_id.is_(None)
                )
            )

        # Filter by agent tier permissions
        allowed_categories = self._get_allowed_categories(agent_tier)
        if category:
            if category in allowed_categories:
                query = query.filter(UserPreference.category == category)
            else:
                return []  # Agent not allowed to access this category
        else:
            query = query.filter(UserPreference.category.in_(allowed_categories))

        # For task agents, only show preferences relevant to their scope
        if agent_tier.startswith('3'):
            query = query.filter(
                or_(
                    UserPreference.scope == "global",
                    and_(
                        UserPreference.scope == "agent",
                        UserPreference.scope_target_id == agent_id
                    )
                )
            )

        return query.all()

    def agent_can_modify(
        self,
        preference: UserPreference,
        agent_tier: str,
        agent_id: str
    ) -> bool:
        """Check if an agent can modify a specific preference."""
        if not preference.is_agent_editable(agent_tier):
            return False

        # Task agents can only modify their own scoped preferences
        if agent_tier.startswith('3'):
            if preference.scope == "agent" and preference.scope_target_id != agent_id:
                return False
            if preference.scope == "task" and preference.scope_target_id != agent_id:
                return False

        return True

    def set_preference_by_agent(
        self,
        key: str,
        value: Any,
        agent_tier: str,
        agent_id: str,
        user_id: Optional[str] = None,
        change_reason: Optional[str] = None
    ) -> Tuple[bool, str, Optional[UserPreference]]:
        """
        Set a preference via agent tool.
        Returns: (success, message, preference)
        """
        # Get existing preference
        pref = self.get_preference(key, user_id)

        if pref:
            # Check if agent can modify
            if not self.agent_can_modify(pref, agent_tier, agent_id):
                return False, f"Agent {agent_id} (tier {agent_tier}) not authorized to modify '{key}'", None

            # Update
            self._log_change(pref, pref.get_value(), value, agent_id, change_reason or f"Modified by agent {agent_id}")
            pref.set_value(value, agent_id)
            pref.last_agent_modified_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(pref)
            return True, f"Preference '{key}' updated successfully", pref

        # Creating new preference - check if agent tier allows
        if agent_tier.startswith('3'):
            return False, "Task agents cannot create new preferences", None

        # Determine category from key
        category = key.split('.')[0] if '.' in key else PreferenceCategory.CUSTOM

        new_pref = self.set_preference(
            key=key,
            value=value,
            user_id=user_id,
            category=category,
            modified_by_agent=agent_id,
            change_reason=change_reason or f"Created by agent {agent_id}"
        )

        return True, f"Preference '{key}' created successfully", new_pref

    # ═══════════════════════════════════════════════════════════
    # Optimization & Cleanup
    # ═══════════════════════════════════════════════════════════

    def optimize_preferences(self) -> Dict[str, Any]:
        """
        Optimize preferences: remove duplicates, clean unused, compress history.
        Returns optimization summary.
        """
        results = {
            'duplicates_removed': 0,
            'unused_cleaned': 0,
            'history_compressed': 0,
            'conflicts_resolved': 0
        }

        # 1. Remove duplicate preferences (same key, same scope, same user)
        duplicates = self.db.query(
            UserPreference.key,
            UserPreference.user_id,
            UserPreference.scope,
            UserPreference.scope_target_id,
            func.count('*').label('count')
        ).filter(
            UserPreference.is_active == True
        ).group_by(
            UserPreference.key,
            UserPreference.user_id,
            UserPreference.scope,
            UserPreference.scope_target_id
        ).having(func.count('*') > 1).all()

        for dup in duplicates:
            # Keep the most recently updated, delete others
            prefs = self.db.query(UserPreference).filter(
                UserPreference.key == dup.key,
                UserPreference.user_id == dup.user_id,
                UserPreference.scope == dup.scope,
                UserPreference.scope_target_id == dup.scope_target_id,
                UserPreference.is_active == True
            ).order_by(UserPreference.updated_at.desc()).all()

            # Keep first (most recent), delete rest
            for pref in prefs[1:]:
                pref.deactivate()
                results['duplicates_removed'] += 1

        # 2. Clean unused preferences (not accessed in 90 days, no history)
        cutoff = datetime.utcnow() - timedelta(days=90)
        unused = self.db.query(UserPreference).filter(
            UserPreference.is_active == True,
            UserPreference.updated_at < cutoff,
            UserPreference.last_agent_modified_at.is_(None)
        ).all()

        for pref in unused:
            # Check if it has history
            has_history = self.db.query(UserPreferenceHistory).filter(
                UserPreferenceHistory.preference_id == pref.id
            ).first()

            if not has_history:
                pref.deactivate()
                results['unused_cleaned'] += 1

        # 3. Compress old history (keep last 10 entries per preference)
        pref_ids = self.db.query(UserPreference.id).filter(
            UserPreference.is_active == True
        ).all()

        for (pref_id,) in pref_ids:
            old_history = self.db.query(UserPreferenceHistory).filter(
                UserPreferenceHistory.preference_id == pref_id
            ).order_by(UserPreferenceHistory.created_at.desc()).offset(10).all()

            for hist in old_history:
                hist.deactivate()
                results['history_compressed'] += 1

        self.db.commit()

        # Log optimization
        audit = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.GOVERNANCE,
            actor_type="system",
            actor_id="PREFERENCE_OPTIMIZER",
            action="preferences_optimized",
            description=f"Preference optimization completed",
            after_state=results
        )
        self.db.add(audit)

        return results

    def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Get recommendations for preference optimization."""
        recommendations = []

        # Find preferences with conflicting values (user vs system)
        system_prefs = self.db.query(UserPreference).filter(
            UserPreference.user_id.is_(None),
            UserPreference.is_active == True
        ).all()

        for sys_pref in system_prefs:
            user_override = self.db.query(UserPreference).filter(
                UserPreference.key == sys_pref.key,
                UserPreference.user_id.isnot(None),
                UserPreference.is_active == True
            ).first()

            if user_override and user_override.get_value() != sys_pref.get_value():
                recommendations.append({
                    'type': 'conflict',
                    'key': sys_pref.key,
                    'system_value': sys_pref.get_value(),
                    'user_value': user_override.get_value(),
                    'recommendation': 'Consider syncing values or documenting override reason'
                })

        # Find preferences with many history entries (high churn)
        high_churn = self.db.query(
            UserPreferenceHistory.preference_id,
            func.count('*').label('change_count')
        ).group_by(
            UserPreferenceHistory.preference_id
        ).having(func.count('*') > 20).all()

        for churn in high_churn:
            pref = self.db.query(UserPreference).filter_by(id=churn.preference_id).first()
            if pref:
                recommendations.append({
                    'type': 'high_churn',
                    'key': pref.key,
                    'change_count': churn.change_count,
                    'recommendation': 'Consider if this preference should be auto-calculated instead of manual'
                })

        return recommendations

    # ═══════════════════════════════════════════════════════════
    # Helper Methods
    # ═══════════════════════════════════════════════════════════

    def _detect_data_type(self, value: Any) -> str:
        """Detect the data type of a value."""
        if isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "integer"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, (list, tuple)):
            return "array"
        elif isinstance(value, dict):
            return "json"
        else:
            return "string"

    def _generate_agentium_id(self) -> str:
        """Generate unique agentium ID for preference."""
        # Format: PREF + date + random
        date_part = datetime.utcnow().strftime('%y%m%d')
        random_part = f"{random.randint(0, 9999):04d}"
        return f"PREF{date_part}{random_part}"

    def _get_allowed_categories(self, agent_tier: str) -> List[str]:
        """Get categories an agent tier can access."""
        if agent_tier.startswith('0') or agent_tier.startswith('1'):
            # Head and Council: all categories
            return [
                PreferenceCategory.GENERAL,
                PreferenceCategory.UI,
                PreferenceCategory.NOTIFICATIONS,
                PreferenceCategory.AGENTS,
                PreferenceCategory.TASKS,
                PreferenceCategory.CHAT,
                PreferenceCategory.MODELS,
                PreferenceCategory.TOOLS,
                PreferenceCategory.PRIVACY,
                PreferenceCategory.CUSTOM,
            ]
        elif agent_tier.startswith('2'):
            # Lead agents
            return [
                PreferenceCategory.AGENTS,
                PreferenceCategory.TASKS,
                PreferenceCategory.TOOLS,
                PreferenceCategory.CHAT,
                PreferenceCategory.NOTIFICATIONS,
            ]
        else:
            # Task agents
            return [
                PreferenceCategory.TASKS,
                PreferenceCategory.CHAT,
            ]

    def _log_change(
        self,
        preference: UserPreference,
        old_value: Any,
        new_value: Any,
        agent_id: Optional[str],
        reason: str
    ):
        """Log preference change to history."""
        history = UserPreferenceHistory(
            id=str(uuid.uuid4()),
            agentium_id=self._generate_agentium_id(),
            preference_id=preference.id,
            previous_value_json=json.dumps(old_value) if old_value is not None else "null",
            new_value_json=json.dumps(new_value) if new_value is not None else "null",
            changed_by_agentium_id=agent_id,
            change_reason=reason,
            change_category="agent" if agent_id else "manual"
        )
        self.db.add(history)
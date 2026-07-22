"""
User Preference entity for Agentium.
Stores user preferences in a flexible key-value structure with categories.
Agents can access and modify these preferences via tools.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import Column, String, Text, DateTime, Index, ForeignKey, event
from sqlalchemy.orm import validates, Session
from .base import BaseEntity


class PreferenceCategory:
    """Categories for organizing user preferences."""
    GENERAL = "general"
    UI = "ui"
    NOTIFICATIONS = "notifications"
    AGENTS = "agents"
    TASKS = "tasks"
    CHAT = "chat"
    MODELS = "models"
    TOOLS = "tools"
    PRIVACY = "privacy"
    CUSTOM = "custom"


class UserPreference(BaseEntity):
    """
    User preference storage with hierarchical key structure.
    Supports scoped preferences (global, per-agent, per-task).
    """

    __tablename__ = 'user_preferences'

    # Foreign key to user (nullable for system-wide defaults)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=True, index=True)

    # Preference categorization
    category = Column(String(50), nullable=False, default=PreferenceCategory.GENERAL, index=True)

    # Hierarchical key (e.g., "ui.theme", "agents.3xxxx.timeout", "chat.history_limit")
    key = Column(String(255), nullable=False, index=True)

    # Value stored as JSON string for flexibility
    value_json = Column(Text, nullable=False)

    # Data type for validation
    data_type = Column(String(20), nullable=False, default="string")

    # Scope: "global", "agent", "task", "system"
    scope = Column(String(20), nullable=False, default="global", index=True)

    # For scoped preferences: which agent/task this applies to
    scope_target_id = Column(String(20), nullable=True, index=True)  # agentium_id or task_id

    # Metadata
    description = Column(Text, nullable=True)
    is_editable_by_agents = Column(String(1), default="Y", nullable=False)  # Y/N
    last_modified_by_agent = Column(String(10), nullable=True)  # agentium_id

    # Timestamps (inherited from BaseEntity, but we track agent modifications separately)
    last_agent_modified_at = Column(DateTime, nullable=True)

    # Table indexes for common queries
    __table_args__ = (
        Index('idx_user_pref_user_cat', 'user_id', 'category'),
        Index('idx_user_pref_key_scope', 'key', 'scope', 'scope_target_id'),
        Index('idx_user_pref_agent_editable', 'is_editable_by_agents', 'category'),
    )

    @validates('key')
    def validate_key(self, key, value):
        """Ensure key follows hierarchical dot notation."""
        if not value:
            raise ValueError("Preference key cannot be empty")

        # Normalize: lowercase, replace spaces with underscores
        normalized = value.lower().strip().replace(' ', '_')

        # Validate format: category.subkey or just key
        parts = normalized.split('.')
        if len(parts) > 3:
            raise ValueError("Preference key can have at most 3 levels (category.sub.sub)")

        # Validate characters
        allowed_chars = set('abcdefghijklmnopqrstuvwxyz0123456789._-')
        if not all(c in allowed_chars for c in normalized):
            raise ValueError("Preference key contains invalid characters")

        return normalized

    @validates('value_json')
    def validate_value(self, key, value):
        """Ensure value is valid JSON."""
        if value is None:
            return json.dumps(None)

        # If already a string, validate it's valid JSON
        if isinstance(value, str):
            try:
                json.loads(value)
                return value
            except json.JSONDecodeError:
                raise ValueError("Value must be valid JSON")

        # Convert to JSON string
        return json.dumps(value)

    @validates('data_type')
    def validate_data_type(self, key, value):
        """Ensure valid data type."""
        allowed = ['string', 'integer', 'float', 'boolean', 'json', 'array']
        if value not in allowed:
            raise ValueError(f"Data type must be one of: {allowed}")
        return value

    def get_value(self) -> Any:
        """Get the Python value from JSON storage."""
        try:
            return json.loads(self.value_json)
        except (json.JSONDecodeError, TypeError):
            return None

    def set_value(self, value: Any, agent_id: Optional[str] = None):
        """Set value and track agent modification."""
        self.value_json = json.dumps(value)
        self.last_agent_modified_at = datetime.utcnow()
        if agent_id:
            self.last_modified_by_agent = agent_id

    def to_dict(self, include_value: bool = True) -> Dict[str, Any]:
        """Convert to dictionary."""
        base = super().to_dict()
        base.update({
            'user_id': self.user_id,
            'category': self.category,
            'key': self.key,
            'data_type': self.data_type,
            'scope': self.scope,
            'scope_target_id': self.scope_target_id,
            'description': self.description,
            'is_editable_by_agents': self.is_editable_by_agents == "Y",
            'last_modified_by_agent': self.last_modified_by_agent,
            'last_agent_modified_at': self.last_agent_modified_at.isoformat() if self.last_agent_modified_at else None,
        })

        if include_value:
            base['value'] = self.get_value()

        return base

    def is_agent_editable(self, agent_tier: str) -> bool:
        """Check if an agent can edit this preference."""
        if self.is_editable_by_agents != "Y":
            return False

        # Head and Council can edit any editable preference
        if agent_tier.startswith('0') or agent_tier.startswith('1'):
            return True

        # Lead agents can edit task and agent preferences
        if agent_tier.startswith('2'):
            return self.category in [PreferenceCategory.AGENTS, PreferenceCategory.TASKS, PreferenceCategory.TOOLS]

        # Task agents can only edit specific categories
        if agent_tier.startswith('3'):
            return self.category in [PreferenceCategory.TASKS, PreferenceCategory.CHAT]

        return False

    def __repr__(self):
        return f"<UserPreference(key='{self.key}', category='{self.category}', scope='{self.scope}')>"


class UserPreferenceHistory(BaseEntity):
    """
    Audit trail for preference changes.
    Tracks what was changed, by whom, and when.
    """

    __tablename__ = 'user_preference_history'

    preference_id = Column(String(36), ForeignKey('user_preferences.id'), nullable=False, index=True)

    # What changed
    previous_value_json = Column(Text, nullable=False)
    new_value_json = Column(Text, nullable=False)

    # Who changed it
    changed_by_agentium_id = Column(String(10), nullable=True)  # If agent-modified
    changed_by_user_id = Column(String(36), nullable=True)  # If user-modified

    # Change metadata
    change_reason = Column(Text, nullable=True)
    change_category = Column(String(50), default="manual", nullable=False)  # manual, auto, optimization, task

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        base = super().to_dict()
        base.update({
            'preference_id': self.preference_id,
            'previous_value': json.loads(self.previous_value_json),
            'new_value': json.loads(self.new_value_json),
            'changed_by_agentium_id': self.changed_by_agentium_id,
            'changed_by_user_id': self.changed_by_user_id,
            'change_reason': self.change_reason,
            'change_category': self.change_category,
        })
        return base


# Event listeners for audit trail
@event.listens_for(UserPreference, 'before_update')
def log_preference_change(mapper, connection, target):
    """Log changes to preference history before update."""
    # This runs in the database layer, so we need to get the old value from DB
    # The actual history logging happens in the service layer for better control
    pass
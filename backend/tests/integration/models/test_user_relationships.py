"""
Integration tests for User, UserModelConfig, and UserPreference relationships (3.3.4).
Verifies authentication, FK links, hierarchical preference key validation, and RBAC roles.
"""
import pytest
import json
from datetime import datetime, timezone, timedelta
from backend.models.entities.user import User, ROLE_PRIMARY_SOVEREIGN, ROLE_DEPUTY_SOVEREIGN, ROLE_OBSERVER
from backend.models.entities.user_config import UserModelConfig, ProviderType, ConnectionStatus
from backend.models.entities.user_preference import UserPreference, PreferenceCategory


def test_user_create_and_authenticate(db_session):
    """Verify password hashing and User.verify_password."""
    user = User(
        username="john_doe",
        email="john@example.com",
        hashed_password=User.hash_password("SuperSecret123!"),
        is_active=True,
        role=ROLE_DEPUTY_SOVEREIGN,
    )
    db_session.add(user)
    db_session.commit()

    fetched = db_session.query(User).filter_by(username="john_doe").first()
    assert fetched is not None
    assert fetched.verify_password("SuperSecret123!", fetched.hashed_password) is True
    assert fetched.verify_password("WrongPassword", fetched.hashed_password) is False


def test_user_model_config_fk(db_session, sample_user):
    """Verify UserModelConfig links to User via user_id FK."""
    config = UserModelConfig(
        agentium_id="MC99001",
        user_id=sample_user.id,
        provider=ProviderType.ANTHROPIC,
        config_name="Anthropic Claude Config",
        default_model="claude-3-5-sonnet-20241022",
        status=ConnectionStatus.ACTIVE,
    )
    db_session.add(config)
    db_session.commit()

    fetched = db_session.query(UserModelConfig).filter_by(agentium_id="MC99001").first()
    assert fetched is not None
    assert fetched.user_id == sample_user.id
    assert fetched.provider == ProviderType.ANTHROPIC


def test_user_preference_fk(db_session, sample_user):
    """Verify UserPreference links to User via user_id FK."""
    pref = UserPreference(
        agentium_id="UP99001",
        user_id=sample_user.id,
        category=PreferenceCategory.GENERAL,
        key="general.language",
        value_json=json.dumps("en-US"),
        data_type="string",
    )
    db_session.add(pref)
    db_session.commit()

    fetched = db_session.query(UserPreference).filter_by(agentium_id="UP99001").first()
    assert fetched is not None
    assert fetched.user_id == sample_user.id
    assert fetched.get_value() == "en-US"


def test_user_preference_key_validation():
    """Verify UserPreference key validator enforces hierarchical dot notation."""
    pref = UserPreference()

    # Empty key
    with pytest.raises(ValueError, match="Preference key cannot be empty"):
        pref.validate_key("key", "")

    # More than 3 levels
    with pytest.raises(ValueError, match="at most 3 levels"):
        pref.validate_key("key", "level1.level2.level3.level4")

    # Invalid characters
    with pytest.raises(ValueError, match="invalid characters"):
        pref.validate_key("key", "invalid@key!")

    # Valid key normalization
    assert pref.validate_key("key", "  UI.Theme_Mode ") == "ui.theme_mode"


def test_user_preference_value_validation():
    """Verify UserPreference value_json validation."""
    pref = UserPreference()

    # Valid JSON string
    assert pref.validate_value("value_json", '{"theme": "dark"}') == '{"theme": "dark"}'

    # Invalid JSON string
    with pytest.raises(ValueError, match="must be valid JSON"):
        pref.validate_value("value_json", "{invalid json}")

    # Python dict converted to JSON string
    assert pref.validate_value("value_json", {"a": 1}) == '{"a": 1}'


def test_user_preference_agent_editability():
    """Verify is_agent_editable method respects tier levels and categories."""
    pref = UserPreference(
        category=PreferenceCategory.TASKS,
        is_editable_by_agents="Y",
    )

    # Head / Council tier (0xxxx / 1xxxx)
    assert pref.is_agent_editable("00001") is True
    assert pref.is_agent_editable("10001") is True

    # Lead tier (2xxxx) - can edit TASKS
    assert pref.is_agent_editable("20001") is True

    # Task agent (3xxxx) - can edit TASKS
    assert pref.is_agent_editable("30001") is True

    # Task agent cannot edit PRIVACY
    privacy_pref = UserPreference(
        category=PreferenceCategory.PRIVACY,
        is_editable_by_agents="Y",
    )
    assert privacy_pref.is_agent_editable("30001") is False


def test_user_preference_scoped_targeting(db_session, sample_user):
    """Verify scoped preferences filter by scope and scope_target_id."""
    pref_global = UserPreference(
        agentium_id="UP99002",
        user_id=sample_user.id,
        category=PreferenceCategory.AGENTS,
        key="agents.timeout",
        value_json=json.dumps(60),
        scope="global",
    )
    pref_agent = UserPreference(
        agentium_id="UP99003",
        user_id=sample_user.id,
        category=PreferenceCategory.AGENTS,
        key="agents.timeout",
        value_json=json.dumps(120),
        scope="agent",
        scope_target_id="30001",
    )
    db_session.add_all([pref_global, pref_agent])
    db_session.commit()

    agent_specific = db_session.query(UserPreference).filter_by(scope="agent", scope_target_id="30001").first()
    assert agent_specific is not None
    assert agent_specific.get_value() == 120


def test_user_rbac_effective_role(db_session):
    """Verify User.effective_role, is_sovereign, and can_veto properties."""
    admin_user = User(
        username="admin",
        email="admin@test.com",
        hashed_password="hash",
        is_admin=True,
    )
    assert admin_user.effective_role == ROLE_PRIMARY_SOVEREIGN
    assert admin_user.is_sovereign is True
    assert admin_user.can_veto is True

    deputy_user = User(
        username="deputy",
        email="deputy@test.com",
        hashed_password="hash",
        is_admin=False,
        role=ROLE_DEPUTY_SOVEREIGN,
    )
    assert deputy_user.effective_role == ROLE_DEPUTY_SOVEREIGN
    assert deputy_user.is_sovereign is False
    assert deputy_user.can_veto is True

    # Expired role fallback
    expired_user = User(
        username="temp_sovereign",
        email="temp@test.com",
        hashed_password="hash",
        is_admin=False,
        role=ROLE_DEPUTY_SOVEREIGN,
        role_expires_at=datetime.utcnow() - timedelta(hours=1),
    )
    assert expired_user.effective_role == ROLE_OBSERVER
    assert expired_user.can_veto is False

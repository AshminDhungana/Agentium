"""
Unit tests for User, UserModelConfig, UserPreference, AuditLog, and related models.
Tests all roles, configurations, preferences, audit logs, and violation tracking.
"""
import pytest
import json
from datetime import datetime, timezone, timedelta

from backend.models.entities.user import (
    User, ROLE_PRIMARY_SOVEREIGN, ROLE_DEPUTY_SOVEREIGN, ROLE_OBSERVER
)
from backend.models.entities.user_config import (
    UserModelConfig, ProviderType, ConnectionStatus, ModelUsageLog
)
from backend.models.entities.user_preference import (
    UserPreference, UserPreferenceHistory, PreferenceCategory
)
from backend.models.entities.audit import (
    AuditLog, AuditLevel, AuditCategory, ConstitutionViolation, SessionLog, HealthCheck
)
from backend.models.entities.monitoring import (
    ViolationReport, ViolationSeverity, AgentHealthReport, MonitoringStatus, TaskVerification
)


# =========================================================================
# User Unit Tests
# =========================================================================

class TestUser:
    """Tests for User model."""

    def test_user_creation_with_all_fields(self, db_session):
        """User creates with all required fields."""
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password=User.hash_password("password123"),
            is_active=True,
            is_admin=False,
            is_pending=False,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.is_active is True
        assert user.is_admin is False
        assert user.is_pending is False

    def test_user_defaults(self, db_session):
        """User defaults are correct."""
        user = User(
            username="defaultuser",
            email="default@example.com",
            hashed_password=User.hash_password("password123"),
        )
        db_session.add(user)
        db_session.commit()

        assert user.is_active is False
        assert user.is_admin is False
        assert user.is_pending is True
        assert user.role == ROLE_OBSERVER

    def test_user_role_effective_role(self, db_session):
        """effective_role property works correctly."""
        # Admin user
        admin = User(
            username="admin",
            email="admin@example.com",
            hashed_password=User.hash_password("password"),
            is_admin=True,
            role=ROLE_OBSERVER,
        )
        assert admin.effective_role == ROLE_PRIMARY_SOVEREIGN

        # Deputy sovereign
        deputy = User(
            username="deputy",
            email="deputy@example.com",
            hashed_password=User.hash_password("password"),
            is_admin=False,
            role=ROLE_DEPUTY_SOVEREIGN,
        )
        assert deputy.effective_role == ROLE_DEPUTY_SOVEREIGN

        # Observer
        observer = User(
            username="observer",
            email="observer@example.com",
            hashed_password=User.hash_password("password"),
            is_admin=False,
            role=ROLE_OBSERVER,
        )
        assert observer.effective_role == ROLE_OBSERVER

    def test_user_role_expiry(self, db_session):
        """Role expiry reverts to OBSERVER."""
        user = User(
            username="expiring",
            email="expiring@example.com",
            hashed_password=User.hash_password("password"),
            role=ROLE_DEPUTY_SOVEREIGN,
            role_expires_at=datetime.utcnow() - timedelta(hours=1),  # Expired
        )
        assert user.effective_role == ROLE_OBSERVER

    def test_user_can_veto_property(self, db_session):
        """can_veto property works for sovereign roles."""
        primary = User(
            username="primary",
            email="primary@example.com",
            hashed_password=User.hash_password("password"),
            role=ROLE_PRIMARY_SOVEREIGN,
        )
        assert primary.can_veto is True

        deputy = User(username="dep", email="dep@e.com", hashed_password="x", role=ROLE_DEPUTY_SOVEREIGN)
        assert deputy.can_veto is True

        observer = User(username="obs", email="obs@e.com", hashed_password="x", role=ROLE_OBSERVER)
        assert observer.can_veto is False

    def test_user_is_sovereign_property(self, db_session):
        """is_sovereign property works."""
        primary = User(username="p", email="p@e.com", hashed_password="x", role=ROLE_PRIMARY_SOVEREIGN)
        assert primary.is_sovereign is True

        deputy = User(username="d", email="d@e.com", hashed_password="x", role=ROLE_DEPUTY_SOVEREIGN)
        assert deputy.is_sovereign is False

    def test_user_password_hashing(self):
        """Password hashing and verification works."""
        password = "testpass123"
        hashed = User.hash_password(password)

        assert User.verify_password(password, hashed) is True
        assert User.verify_password("wrongpass", hashed) is False

    def test_user_prehash_long_passwords(self):
        """Long passwords are pre-hashed with SHA-256 before bcrypt."""
        long_password = "a" * 100  # Longer than bcrypt's 72-byte limit
        hashed = User.hash_password(long_password)

        assert User.verify_password(long_password, hashed) is True
        assert User.verify_password("a" * 99, hashed) is False

    def test_user_create_user_classmethod(self, db_session):
        """User.create_user factory method works."""
        user = User.create_user(
            db=db_session,
            username="created",
            email="created@example.com",
            password="password123",
            is_admin=True,
        )

        assert user.username == "created"
        assert user.is_admin is True
        assert user.role == ROLE_PRIMARY_SOVEREIGN

    def test_user_authenticate_classmethod(self, db_session):
        """User.authenticate classmethod works."""
        User.create_user(
            db=db_session,
            username="authtest",
            email="auth@example.com",
            password="correctpass",
        )

        user = User.authenticate(db_session, "authtest", "correctpass")
        assert user is not None
        assert user.username == "authtest"

        # Wrong password
        user = User.authenticate(db_session, "authtest", "wrongpass")
        assert user is None

        # Non-existent user
        user = User.authenticate(db_session, "nonexistent", "password")
        assert user is None

    def test_user_to_dict(self, db_session):
        """User.to_dict includes all relevant fields."""
        user = User(
            username="dictuser",
            email="dict@example.com",
            hashed_password=User.hash_password("password"),
            is_active=True,
            is_admin=False,
            role=ROLE_OBSERVER,
        )
        db_session.add(user)
        db_session.commit()

        data = user.to_dict()

        assert data["username"] == "dictuser"
        assert data["email"] == "dict@example.com"
        assert data["is_active"] is True
        assert data["role"] == ROLE_OBSERVER
        assert data["effective_role"] == ROLE_OBSERVER
        assert data["can_veto"] is False
        assert "hashed_password" not in data

        data_sensitive = user.to_dict(include_sensitive=True)
        assert "hashed_password" in data_sensitive


# =========================================================================
# UserModelConfig Unit Tests
# =========================================================================

class TestUserModelConfig:
    """Tests for UserModelConfig model."""

    @pytest.mark.parametrize("provider", [
        ProviderType.OPENAI,
        ProviderType.ANTHROPIC,
        ProviderType.GEMINI,
        ProviderType.GROQ,
        ProviderType.MISTRAL,
        ProviderType.LOCAL,
        ProviderType.CUSTOM,
        ProviderType.AZURE_OPENAI,
    ])
    def test_all_providers_valid(self, db_session, provider):
        """All provider types are valid."""
        config = UserModelConfig(
            provider=provider,
            config_name=f"Test {provider.value}",
            default_model="test-model",
            user_id=None,  # System config
        )
        db_session.add(config)
        db_session.commit()

        assert config.provider == provider

    def test_config_creation_with_all_fields(self, db_session):
        """Config creates with all fields."""
        config = UserModelConfig(
            provider=ProviderType.OPENAI,
            config_name="OpenAI Config",
            default_model="gpt-4",
            api_base_url="https://api.openai.com/v1",
            max_tokens=4000,
            temperature=0.7,
            top_p=1.0,
            timeout_seconds=60,
            is_default=True,
            user_id=None,
        )
        db_session.add(config)
        db_session.commit()
        db_session.refresh(config)

        assert config.provider == ProviderType.OPENAI
        assert config.config_name == "OpenAI Config"
        assert config.default_model == "gpt-4"
        assert config.max_tokens == 4000
        assert config.temperature == 0.7
        assert config.is_default is True
        assert config.status == ConnectionStatus.TESTING
        assert config.priority == 999

    def test_config_defaults(self, db_session):
        """Config defaults are correct."""
        config = UserModelConfig(
            provider=ProviderType.LOCAL,
            config_name="Local Config",
            default_model="llama3",
        )
        db_session.add(config)
        db_session.commit()

        assert config.status == ConnectionStatus.TESTING
        assert config.max_tokens == 4000
        assert config.temperature == 0.7
        assert config.top_p == 1.0
        assert config.timeout_seconds == 60
        assert config.effort == "none"
        assert config.is_default is False
        assert config.total_requests == 0
        assert config.total_tokens == 0
        assert config.estimated_cost_usd == 0.0
        assert config.requests_per_minute == 60
        assert config.max_concurrent_requests == 10
        assert config.monthly_budget_usd == 0.0
        assert config.current_spend_usd == 0.0
        assert config.failure_count == 0

    def test_config_agentium_id_generation(self, db_session):
        """Config generates agentium_id automatically."""
        config = UserModelConfig(
            provider=ProviderType.OPENAI,
            config_name="Test",
            default_model="gpt-4",
        )
        db_session.add(config)
        db_session.commit()

        assert config.agentium_id is not None
        assert config.agentium_id.startswith("C")
        assert len(config.agentium_id) >= 8  # C + date + random hex

    def test_config_get_effective_base_url_openai(self, db_session):
        """get_effective_base_url returns default for OpenAI."""
        config = UserModelConfig(
            provider=ProviderType.OPENAI,
            config_name="Test",
            default_model="gpt-4",
        )
        db_session.add(config)
        db_session.commit()

        url = config.get_effective_base_url()
        assert url == "https://api.openai.com/v1"

    def test_config_get_effective_base_url_custom(self, db_session):
        """get_effective_base_url returns custom URL when set."""
        config = UserModelConfig(
            provider=ProviderType.OPENAI,
            config_name="Test",
            default_model="gpt-4",
            api_base_url="https://custom.example.com/v1",
        )
        db_session.add(config)
        db_session.commit()

        url = config.get_effective_base_url()
        assert url == "https://custom.example.com/v1"

    def test_config_local_provider(self, db_session):
        """Local provider uses local_server_url or settings."""
        import backend.core.config as settings_module
        original = settings_module.settings.OLLAMA_BASE_URL
        settings_module.settings.OLLAMA_BASE_URL = "http://localhost:11434"

        try:
            config = UserModelConfig(
                provider=ProviderType.LOCAL,
                config_name="Local",
                default_model="llama3",
            )
            db_session.add(config)
            db_session.commit()

            url = config.get_effective_base_url()
            assert url == "http://localhost:11434"
        finally:
            settings_module.settings.OLLAMA_BASE_URL = original

    def test_config_azure_requires_explicit_url(self, db_session):
        """Azure OpenAI requires explicit base URL."""
        config = UserModelConfig(
            provider=ProviderType.AZURE_OPENAI,
            config_name="Azure",
            default_model="deployment-1",
        )
        db_session.add(config)
        db_session.commit()

        url = config.get_effective_base_url()
        assert url is None

    def test_config_custom_requires_explicit_url(self, db_session):
        """CUSTOM provider requires explicit base URL."""
        config = UserModelConfig(
            provider=ProviderType.CUSTOM,
            config_name="Custom",
            default_model="my-model",
        )
        db_session.add(config)
        db_session.commit()

        url = config.get_effective_base_url()
        assert url is None

    def test_config_requires_api_key(self, db_session):
        """requires_api_key works correctly."""
        local = UserModelConfig(provider=ProviderType.LOCAL, config_name="L", default_model="m")
        openai = UserModelConfig(provider=ProviderType.OPENAI, config_name="O", default_model="m")

        assert local.requires_api_key() is False
        assert openai.requires_api_key() is True

    def test_config_health_check(self, db_session):
        """is_key_healthy checks correctly."""
        # Healthy config
        config = UserModelConfig(
            provider=ProviderType.OPENAI,
            config_name="Healthy",
            default_model="gpt-4",
            status=ConnectionStatus.ACTIVE,
        )
        db_session.add(config)
        db_session.commit()

        assert config.is_key_healthy() is True

        # Error status
        config.status = ConnectionStatus.ERROR
        db_session.commit()
        assert config.is_key_healthy() is False

        # Cooldown
        config.status = ConnectionStatus.ACTIVE
        config.cooldown_until = datetime.utcnow() + timedelta(minutes=5)
        db_session.commit()
        assert config.is_key_healthy() is False
        config.cooldown_until = None
        db_session.commit()

        # Budget exceeded
        config.monthly_budget_usd = 10.0
        config.current_spend_usd = 15.0
        db_session.commit()
        assert config.is_key_healthy() is False

    def test_config_failure_and_success_recording(self, db_session):
        """record_failure and record_success work."""
        config = UserModelConfig(
            provider=ProviderType.OPENAI,
            config_name="Test",
            default_model="gpt-4",
        )
        db_session.add(config)
        db_session.commit()

        # First failure - status remains TESTING (default)
        config.record_failure()
        db_session.commit()
        assert config.failure_count == 1
        assert config.status == ConnectionStatus.TESTING  # Default status unchanged

        # Second failure
        config.record_failure()
        db_session.commit()
        assert config.failure_count == 2

        # Third failure triggers cooldown and ERROR status
        config.record_failure()
        db_session.commit()
        assert config.failure_count >= 3
        assert config.status == ConnectionStatus.ERROR
        assert config.cooldown_until is not None

        # Success resets
        config.record_success()
        db_session.commit()
        assert config.failure_count == 0
        assert config.status == ConnectionStatus.ACTIVE
        assert config.cooldown_until is None

    def test_config_spend_tracking(self, db_session):
        """record_spend tracks and resets monthly."""
        config = UserModelConfig(
            provider=ProviderType.OPENAI,
            config_name="Spend",
            default_model="gpt-4",
            monthly_budget_usd=100.0,
        )
        db_session.add(config)
        db_session.commit()

        config.record_spend(0.05)
        db_session.commit()
        assert config.current_spend_usd == 0.05

        config.record_spend(0.03)
        db_session.commit()
        assert config.current_spend_usd == 0.08

    def test_config_spend_monthly_reset(self, db_session):
        """record_spend resets at month boundary."""
        config = UserModelConfig(
            provider=ProviderType.OPENAI,
            config_name="Reset",
            default_model="gpt-4",
        )
        db_session.add(config)
        db_session.commit()

        # Set last_spend_reset to previous month
        config.last_spend_reset = datetime.utcnow() - timedelta(days=31)
        config.current_spend_usd = 50.0
        db_session.commit()

        config.record_spend(5.0)
        db_session.commit()

        # Should have reset
        assert config.current_spend_usd == 5.0

    def test_config_mask_key(self, db_session):
        """mask_key_for_display stores masked version."""
        config = UserModelConfig(
            provider=ProviderType.OPENAI,
            config_name="Mask",
            default_model="gpt-4",
        )
        db_session.add(config)
        db_session.commit()

        config.mask_key_for_display("sk-abcdefghijklmnop")
        db_session.commit()
        assert config.api_key_masked == "...mnop"

        config.mask_key_for_display("short")
        db_session.commit()
        # For short strings, model takes last 4 chars
        assert config.api_key_masked == "...hort"

    def test_config_to_dict(self, db_session):
        """to_dict includes all fields."""
        config = UserModelConfig(
            provider=ProviderType.OPENAI,
            config_name="Dict Config",
            default_model="gpt-4",
            api_base_url="https://api.openai.com/v1",
            max_tokens=2000,
            temperature=0.5,
            is_default=True,
        )
        db_session.add(config)
        db_session.commit()

        data = config.to_dict()

        assert data["provider"] == "OPENAI"
        assert data["config_name"] == "Dict Config"
        assert data["default_model"] == "gpt-4"
        assert data["api_base_url"] == "https://api.openai.com/v1"
        assert data["settings"]["max_tokens"] == 2000
        assert data["settings"]["temperature"] == 0.5
        assert data["is_default"] is True
        assert "api_key" not in data  # Not included by default

    def test_config_increment_usage(self, db_session):
        """increment_usage tracks usage."""
        config = UserModelConfig(
            provider=ProviderType.OPENAI,
            config_name="Usage",
            default_model="gpt-4",
        )
        db_session.add(config)
        db_session.commit()

        config.increment_usage(tokens=100, cost_usd=0.01)
        db_session.commit()

        assert config.total_requests == 1
        assert config.total_tokens == 100
        assert config.estimated_cost_usd == 0.01
        assert config.last_used_at is not None


# =========================================================================
# ModelUsageLog Unit Tests
# =========================================================================

class TestModelUsageLog:
    """Tests for ModelUsageLog model."""

    def test_usage_log_creation(self, db_session):
        """Usage log creates with required fields."""
        config = UserModelConfig(
            provider=ProviderType.OPENAI,
            config_name="Config",
            default_model="gpt-4",
        )
        db_session.add(config)
        db_session.commit()

        log = ModelUsageLog(
            config_id=config.id,
            provider=ProviderType.OPENAI,
            model_used="gpt-4",
            total_tokens=150,
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=500,
            success=True,
            cost_usd=0.002,
        )
        db_session.add(log)
        db_session.commit()

        assert log.config_id == config.id
        assert log.provider == ProviderType.OPENAI
        assert log.model_used == "gpt-4"
        assert log.total_tokens == 150
        assert log.success is True
        assert log.cost_usd == 0.002


# =========================================================================
# UserPreference Unit Tests
# =========================================================================

class TestUserPreference:
    """Tests for UserPreference model."""

    def test_preference_creation(self, db_session):
        """Preference creates with all fields."""
        user = User(
            username="prefuser",
            email="pref@example.com",
            hashed_password=User.hash_password("pass"),
        )
        db_session.add(user)
        db_session.commit()

        pref = UserPreference(
            user_id=user.id,
            category=PreferenceCategory.UI,
            key="theme",
            value_json=json.dumps("dark"),
            data_type="string",
            scope="global",
            agentium_id="UPF00001",  # Required by BaseEntity
        )
        db_session.add(pref)
        db_session.commit()

        assert pref.user_id == user.id
        assert pref.category == PreferenceCategory.UI
        assert pref.key == "theme"
        assert pref.get_value() == "dark"
        assert pref.data_type == "string"
        assert pref.scope == "global"

    def test_preference_key_normalization(self, db_session):
        """Key is normalized to lowercase with underscores."""
        user = User(username="norm", email="norm@e.com", hashed_password="x")
        db_session.add(user)
        db_session.commit()

        pref = UserPreference(
            user_id=user.id,
            category=PreferenceCategory.GENERAL,
            key="  UI.Theme.Color  ",
            value_json=json.dumps("blue"),
            agentium_id="UPF00002",
        )
        db_session.add(pref)
        db_session.commit()

        assert pref.key == "ui.theme.color"

    def test_preference_key_validation(self, db_session):
        """Invalid keys raise ValueError."""
        user = User(username="val", email="val@e.com", hashed_password="x")
        db_session.add(user)
        db_session.commit()

        # Too many levels - validation happens at object creation
        with pytest.raises(ValueError):
            pref = UserPreference(
                user_id=user.id,
                category=PreferenceCategory.GENERAL,
                key="a.b.c.d",
                value_json=json.dumps("test"),
                agentium_id="UPF00003",
            )
            db_session.add(pref)
            db_session.commit()

        # Invalid characters - validation happens at object creation
        with pytest.raises(ValueError):
            pref2 = UserPreference(
                user_id=user.id,
                category=PreferenceCategory.GENERAL,
                key="invalid@key",
                value_json=json.dumps("test"),
                agentium_id="UPF00004",
            )
            db_session.add(pref2)
            db_session.commit()

    def test_preference_value_json_validation(self, db_session):
        """Value must be valid JSON."""
        user = User(username="val2", email="val2@e.com", hashed_password="x")
        db_session.add(user)
        db_session.commit()

        # Validation happens at object creation when setting value_json
        with pytest.raises(ValueError):
            pref = UserPreference(
                user_id=user.id,
                category=PreferenceCategory.GENERAL,
                key="test",
                value_json="not valid json",
                agentium_id="UPF00005",
            )
            db_session.add(pref)
            db_session.commit()

    def test_preference_data_type_validation(self, db_session):
        """Data type must be one of allowed values."""
        user = User(username="val3", email="val3@e.com", hashed_password="x")
        db_session.add(user)
        db_session.commit()

        # Validation happens at object creation
        with pytest.raises(ValueError):
            pref = UserPreference(
                user_id=user.id,
                category=PreferenceCategory.GENERAL,
                key="test",
                value_json=json.dumps("test"),
                data_type="invalid_type",
                agentium_id="UPF00006",
            )
            db_session.add(pref)
            db_session.commit()

    def test_preference_get_value(self, db_session):
        """get_value returns parsed Python value."""
        user = User(username="getval", email="gv@e.com", hashed_password="x")
        db_session.add(user)
        db_session.commit()

        test_values = [
            ("string", json.dumps("hello"), "hello"),
            ("integer", json.dumps(42), 42),
            ("float", json.dumps(3.14), 3.14),
            ("boolean", json.dumps(True), True),
            ("json", json.dumps({"nested": "object"}), {"nested": "object"}),
            ("array", json.dumps([1, 2, 3]), [1, 2, 3]),
        ]

        for i, (data_type, json_val, expected) in enumerate(test_values):
            pref = UserPreference(
                user_id=user.id,
                category=PreferenceCategory.GENERAL,
                key=f"test.{data_type}",
                value_json=json_val,
                data_type=data_type,
                agentium_id=f"UPF000{i+7:02d}",
            )
            db_session.add(pref)
            db_session.commit()

            assert pref.get_value() == expected

    def test_preference_set_value(self, db_session):
        """set_value updates value and tracks modifications."""
        user = User(username="setval", email="sv@e.com", hashed_password="x")
        db_session.add(user)
        db_session.commit()

        pref = UserPreference(
            user_id=user.id,
            category=PreferenceCategory.GENERAL,
            key="theme",
            value_json=json.dumps("light"),
            agentium_id="UPF00014",
        )
        db_session.add(pref)
        db_session.commit()

        pref.set_value("dark", agent_id="30001")
        db_session.commit()

        assert pref.get_value() == "dark"
        assert pref.last_modified_by_agent == "30001"
        assert pref.last_agent_modified_at is not None

    def test_preference_scoped_agent(self, db_session):
        """Scoped preference with agent target works."""
        user = User(username="scope", email="scope@e.com", hashed_password="x")
        db_session.add(user)
        db_session.commit()

        pref = UserPreference(
            user_id=user.id,
            category=PreferenceCategory.AGENTS,
            key="timeout",
            value_json=json.dumps(300),
            scope="agent",
            scope_target_id="30001",
            agentium_id="UPF00015",
        )
        db_session.add(pref)
        db_session.commit()

        assert pref.scope == "agent"
        assert pref.scope_target_id == "30001"

    def test_preference_agent_editable(self, db_session):
        """is_agent_editable respects tier permissions."""
        user = User(username="edit", email="edit@e.com", hashed_password="x")
        db_session.add(user)
        db_session.commit()

        # Head agent (0xxxx)
        pref1 = UserPreference(
            user_id=user.id,
            category=PreferenceCategory.UI,
            key="theme",
            value_json=json.dumps("dark"),
            is_editable_by_agents="Y",
            agentium_id="UPF00016",
        )
        db_session.add(pref1)
        db_session.commit()
        assert pref1.is_agent_editable("00001") is True

        # Lead agent (2xxxx) - can edit tasks, agents, tools
        pref2 = UserPreference(
            user_id=user.id,
            category=PreferenceCategory.TASKS,
            key="default_priority",
            value_json=json.dumps("normal"),
            is_editable_by_agents="Y",
            agentium_id="UPF00017",
        )
        db_session.add(pref2)
        db_session.commit()
        assert pref2.is_agent_editable("20001") is True

        # Task agent (3xxxx) - can only edit tasks, chat
        assert pref2.is_agent_editable("30001") is True
        assert pref1.is_agent_editable("30001") is False  # UI not editable by task agents

    def test_preference_to_dict(self, db_session):
        """to_dict includes all fields."""
        user = User(username="dictpref", email="dp@e.com", hashed_password="x")
        db_session.add(user)
        db_session.commit()

        pref = UserPreference(
            user_id=user.id,
            category=PreferenceCategory.UI,
            key="theme",
            value_json=json.dumps("dark"),
            scope="global",
            description="User theme preference",
            agentium_id="UPF00018",
        )
        db_session.add(pref)
        db_session.commit()

        data = pref.to_dict()

        assert data["user_id"] == user.id
        assert data["category"] == "ui"
        assert data["key"] == "theme"
        assert data["value"] == "dark"
        assert data["scope"] == "global"
        assert data["description"] == "User theme preference"


# =========================================================================
# UserPreferenceHistory Unit Tests
# =========================================================================

class TestUserPreferenceHistory:
    """Tests for UserPreferenceHistory model."""

    def test_history_creation(self, db_session):
        """History entry creates correctly."""
        user = User(username="hist", email="hist@e.com", hashed_password="x")
        db_session.add(user)
        db_session.commit()

        pref = UserPreference(
            user_id=user.id,
            category=PreferenceCategory.UI,
            key="theme",
            value_json=json.dumps("light"),
            agentium_id="UPF00019",
        )
        db_session.add(pref)
        db_session.commit()

        history = UserPreferenceHistory(
            preference_id=pref.id,
            previous_value_json=json.dumps("light"),
            new_value_json=json.dumps("dark"),
            changed_by_agentium_id="20001",
            change_reason="User preference update",
            change_category="manual",
            agentium_id="UPH00001",
        )
        db_session.add(history)
        db_session.commit()

        assert history.preference_id == pref.id
        # Model stores values as JSON strings, parse them
        assert json.loads(history.previous_value_json) == "light"
        assert json.loads(history.new_value_json) == "dark"
        assert history.changed_by_agentium_id == "20001"

    def test_history_to_dict(self, db_session):
        """History to_dict works."""
        user = User(username="hist2", email="hist2@e.com", hashed_password="x")
        db_session.add(user)
        db_session.commit()

        pref = UserPreference(
            user_id=user.id,
            category=PreferenceCategory.GENERAL,
            key="lang",
            value_json=json.dumps("en"),
            agentium_id="UPF00020",
        )
        db_session.add(pref)
        db_session.commit()

        history = UserPreferenceHistory(
            preference_id=pref.id,
            previous_value_json=json.dumps("en"),
            new_value_json=json.dumps("fr"),
            changed_by_user_id=user.id,
            change_reason="Language change",
            agentium_id="UPH00002",
        )
        db_session.add(history)
        db_session.commit()

        data = history.to_dict()

        assert data["previous_value"] == "en"
        assert data["new_value"] == "fr"
        assert data["changed_by_user_id"] == user.id
        assert data["change_reason"] == "Language change"


# =========================================================================
# AuditLog Unit Tests
# =========================================================================

class TestAuditLog:
    """Tests for AuditLog model."""

    def test_audit_log_creation(self, db_session):
        """AuditLog creates with required fields."""
        audit = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.AGENT_LIFECYCLE,
            actor_type="agent",
            actor_id="30001",
            action="task_assigned",
            target_type="task",
            target_id="task-uuid-123",
            description="Task T00001 assigned to agent 30001",
            success=True,
        )
        db_session.add(audit)
        db_session.commit()
        db_session.refresh(audit)

        assert audit.level == AuditLevel.INFO
        assert audit.category == AuditCategory.AGENT_LIFECYCLE
        assert audit.actor_type == "agent"
        assert audit.actor_id == "30001"
        assert audit.action == "task_assigned"
        assert audit.target_type == "task"
        assert audit.target_id == "task-uuid-123"
        assert audit.success == 'Y'
        assert audit.agentium_id is not None

    @pytest.mark.parametrize("level", [
        AuditLevel.DEBUG,
        AuditLevel.INFO,
        AuditLevel.NOTICE,
        AuditLevel.WARNING,
        AuditLevel.CRITICAL,
        AuditLevel.EMERGENCY,
    ])
    def test_all_audit_levels(self, db_session, level):
        """All audit levels are valid."""
        audit = AuditLog.log(
            level=level,
            category=AuditCategory.SYSTEM,
            actor_type="system",
            actor_id="SYSTEM",
            action="test",
        )
        db_session.add(audit)
        db_session.commit()

        assert audit.level == level

    @pytest.mark.parametrize("category", [
        AuditCategory.SYSTEM,
        AuditCategory.AGENT_LIFECYCLE,
        AuditCategory.CONSTITUTION,
        AuditCategory.TASK,
        AuditCategory.VOTING,
        AuditCategory.AUTHENTICATION,
        AuditCategory.AUTHORIZATION,
        AuditCategory.COMMUNICATION,
        AuditCategory.EXECUTION,
        AuditCategory.DATA_ACCESS,
        AuditCategory.EXTERNAL_API,
        AuditCategory.SECURITY,
        AuditCategory.GOVERNANCE,
    ])
    def test_all_categories(self, db_session, category):
        """All audit categories are valid."""
        audit = AuditLog.log(
            level=AuditLevel.INFO,
            category=category,
            actor_type="system",
            actor_id="SYSTEM",
            action="test",
        )
        db_session.add(audit)
        db_session.commit()

        assert audit.category == category

    def test_audit_log_with_state(self, db_session):
        """AuditLog captures before/after state."""
        before = {"status": "pending", "assignee": None}
        after = {"status": "assigned", "assignee": "30001"}
        meta = {"source": "api", "request_id": "req-123"}

        audit = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.TASK,
            actor_type="agent",
            actor_id="10001",
            action="task_status_change",
            before_state=before,
            after_state=after,
            meta_data=meta,
        )
        db_session.add(audit)
        db_session.commit()
        db_session.refresh(audit)

        assert audit.before_state is not None
        assert json.loads(audit.before_state) == before
        assert json.loads(audit.after_state) == after
        assert json.loads(audit.metadata_json) == meta

    def test_audit_log_actor_id_truncation(self, db_session):
        """Long actor_id is truncated to 100 chars."""
        long_actor_id = "a" * 150
        audit = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.SYSTEM,
            actor_type="system",
            actor_id=long_actor_id,
            action="test",
        )
        db_session.add(audit)
        db_session.commit()

        assert len(audit.actor_id) == 100

    def test_audit_log_system_log_shortcut(self, db_session):
        """system_log shortcut works."""
        audit = AuditLog.system_log(
            action="system_startup",
            description="Agentium system started",
            level=AuditLevel.NOTICE,
        )
        db_session.add(audit)
        db_session.commit()

        assert audit.actor_type == "system"
        assert audit.actor_id == "SYSTEM"
        assert audit.category == AuditCategory.SYSTEM
        assert audit.action == "system_startup"
        assert audit.level == AuditLevel.NOTICE

    def test_audit_log_security_log_shortcut(self, db_session):
        """security_log shortcut works."""
        audit = AuditLog.security_log(
            action="unauthorized_access",
            actor_id="30099",
            description="Agent attempted unauthorized tool access",
            success=False,
        )
        db_session.add(audit)
        db_session.commit()

        assert audit.category == AuditCategory.SECURITY
        assert audit.actor_id == "30099"
        assert audit.success == 'N'
        assert audit.level in (AuditLevel.CRITICAL, AuditLevel.WARNING)

    def test_audit_log_child_event(self, db_session):
        """add_child_event links related events."""
        parent = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.TASK,
            actor_type="agent",
            actor_id="10001",
            action="task_created",
        )
        db_session.add(parent)
        db_session.commit()

        child = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.TASK,
            actor_type="agent",
            actor_id="30001",
            action="task_started",
        )
        db_session.add(child)
        db_session.commit()

        parent.add_child_event(child)
        db_session.commit()

        assert child.parent_audit_id == parent.id
        assert child.correlation_id == parent.correlation_id or child.correlation_id == parent.id

    def test_audit_log_to_dict(self, db_session):
        """to_dict includes all relevant fields."""
        audit = AuditLog.log(
            level=AuditLevel.WARNING,
            category=AuditCategory.SECURITY,
            actor_type="agent",
            actor_id="30099",
            action="unauthorized_action",
            description="Attempted constitution modification",
            success=False,
            error_code="UNAUTHORIZED",
            error_details="Agent lacks permission",
        )
        db_session.add(audit)
        db_session.commit()

        data = audit.to_dict()

        assert data["level"] == "warning"
        assert data["category"] == "security"
        assert data["actor"]["type"] == "agent"
        assert data["actor"]["id"] == "30099"
        assert data["action"] == "unauthorized_action"
        assert data["result"]["success"] is False
        assert data["result"]["error"] == "UNAUTHORIZED"


# =========================================================================
# ConstitutionViolation Unit Tests
# =========================================================================

class TestConstitutionViolation:
    """Tests for ConstitutionViolation model."""

    def test_violation_creation(self, db_session):
        """ConstitutionViolation creates with required fields."""
        violation = ConstitutionViolation(
            agentium_id="30001",
            violation_type="unauthorized_tool_use",
            violated_article="Article 5",
            description="Agent 30001 used tool 'delete_database' without authorization",
            severity=AuditLevel.CRITICAL,
            attempted_action="Tool: delete_database, target: production_db",
            context=json.dumps({"tool": "delete_database", "args": {"force": True}}),
            detected_by="10001",
            detection_method="pre_execution_check",
            blocked=True,
            auto_terminated=False,
        )
        db_session.add(violation)
        db_session.commit()
        db_session.refresh(violation)

        assert violation.agentium_id == "30001"
        assert violation.violation_type == "unauthorized_tool_use"
        assert violation.violated_article == "Article 5"
        assert violation.severity == AuditLevel.CRITICAL
        assert violation.blocked is True
        assert violation.auto_terminated is False

    def test_violation_defaults(self, db_session):
        """ConstitutionViolation defaults are correct."""
        violation = ConstitutionViolation(
            agentium_id="30002",
            violation_type="test",
            description="Test violation",
            attempted_action="test action",
            detected_by="10001",
        )
        db_session.add(violation)
        db_session.commit()

        assert violation.severity == AuditLevel.WARNING
        assert violation.blocked is True
        assert violation.auto_terminated is False
        assert violation.reviewed_by_sovereign is False

    def test_violation_mark_reviewed(self, db_session):
        """mark_reviewed works correctly."""
        violation = ConstitutionViolation(
            agentium_id="30003",
            violation_type="test",
            description="Test",
            attempted_action="test action",
            detected_by="10001",
        )
        db_session.add(violation)
        db_session.commit()

        violation.mark_reviewed("override", "Approved for emergency")
        db_session.commit()

        assert violation.reviewed_by_sovereign is True
        assert violation.sovereign_decision == "override"
        assert violation.review_notes == "Approved for emergency"

    def test_violation_escalate(self, db_session):
        """escalate alerts Head of Council."""
        violation = ConstitutionViolation(
            agentium_id="30004",
            violation_type="test",
            description="Test",
            attempted_action="test action",
            detected_by="10001",
        )
        db_session.add(violation)
        db_session.commit()

        violation.escalate("00001")
        db_session.commit()

        assert violation.escalated_to == "00001"

    def test_violation_to_dict(self, db_session):
        """to_dict includes all fields."""
        violation = ConstitutionViolation(
            agentium_id="30005",
            violation_type="constitution_modification",
            violated_article="Article 1",
            description="Attempted to modify supreme article",
            severity=AuditLevel.EMERGENCY,
            attempted_action="modify constitution",
            detected_by="10001",
            blocked=True,
            auto_terminated=True,
        )
        db_session.add(violation)
        db_session.commit()

        data = violation.to_dict()

        assert data["violator"] == "30005"
        assert data["type"] == "constitution_modification"
        assert data["article"] == "Article 1"
        assert data["severity"] == "emergency"
        assert data["blocked"] is True
        assert data["auto_terminated"] is True
        assert data["reviewed"] is False


# =========================================================================
# ViolationReport Unit Tests
# =========================================================================

class TestViolationReport:
    """Tests for ViolationReport model."""

    def test_violation_report_creation(self, db_session):
        """ViolationReport creates correctly."""
        report = ViolationReport(
            reporter_agent_id="reporter-uuid",
            reporter_agentium_id="10001",
            violator_agent_id="violator-uuid",
            violator_agentium_id="30015",
            severity=ViolationSeverity.MAJOR,
            violated_article="Article 7",
            violation_type="output_manipulation",
            description="Task agent modified output to hide errors",
            evidence=json.dumps([{"type": "log", "content": "..." }]),
            context=json.dumps({"task_id": "T00042", "output_hash": "abc"}),
            agentium_id="VIO00001",
        )
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        assert report.reporter_agentium_id == "10001"
        assert report.violator_agentium_id == "30015"
        assert report.severity == ViolationSeverity.MAJOR
        assert report.violated_article == "Article 7"
        assert report.violation_type == "output_manipulation"
        assert report.status == "open"

    @pytest.mark.parametrize("severity", [
        ViolationSeverity.MINOR,
        ViolationSeverity.MODERATE,
        ViolationSeverity.MAJOR,
        ViolationSeverity.CRITICAL,
    ])
    def test_all_severities(self, db_session, severity):
        """All violation severities are valid."""
        report = ViolationReport(
            reporter_agent_id="r1", reporter_agentium_id="10001",
            violator_agent_id="v1", violator_agentium_id="30001",
            severity=severity,
            violation_type="test",
            description="Test",
            agentium_id=f"VIO{severity.value[:3].upper()}001",
        )
        db_session.add(report)
        db_session.commit()

        assert report.severity == severity

    def test_report_assign_investigation(self, db_session):
        """assign_investigation works."""
        report = ViolationReport(
            reporter_agent_id="r1", reporter_agentium_id="10001",
            violator_agent_id="v1", violator_agentium_id="30001",
            severity=ViolationSeverity.MAJOR,
            violation_type="test",
            description="Test",
            agentium_id="VIO00002",
        )
        db_session.add(report)
        db_session.commit()

        report.assign_investigation("00001")
        db_session.commit()

        assert report.assigned_to == "00001"
        assert report.status == "investigating"

    def test_report_resolve(self, db_session):
        """resolve marks violation as resolved."""
        report = ViolationReport(
            reporter_agent_id="r1", reporter_agentium_id="10001",
            violator_agent_id="v1", violator_agentium_id="30001",
            severity=ViolationSeverity.MODERATE,
            violation_type="test",
            description="Test",
            agentium_id="VIO00003",
        )
        db_session.add(report)
        db_session.commit()

        report.resolve("suspension", "Suspended for 24 hours", terminated=False)
        db_session.commit()

        assert report.status == "resolved"
        assert report.action_taken == "suspension"
        assert report.resolution == "Suspended for 24 hours"
        assert report.violator_terminated is False

    def test_report_resolve_with_termination(self, db_session):
        """resolve with termination works."""
        report = ViolationReport(
            reporter_agent_id="r1", reporter_agentium_id="10001",
            violator_agent_id="v1", violator_agentium_id="30001",
            severity=ViolationSeverity.CRITICAL,
            violation_type="security_breach",
            description="Critical breach",
            agentium_id="VIO00004",
        )
        db_session.add(report)
        db_session.commit()

        report.resolve("termination", "Immediate termination", terminated=True)
        db_session.commit()

        assert report.violator_terminated is True

    def test_report_to_dict(self, db_session):
        """to_dict includes all fields."""
        report = ViolationReport(
            reporter_agent_id="r1", reporter_agentium_id="10001",
            violator_agent_id="v1", violator_agentium_id="30001",
            severity=ViolationSeverity.MAJOR,
            violation_type="policy_violation",
            description="Policy violation",
            agentium_id="VIO00005",
        )
        db_session.add(report)
        db_session.commit()

        data = report.to_dict()

        assert data["reporter"] == "10001"
        assert data["violator"] == "30001"
        assert data["severity"] == "major"
        assert data["type"] == "policy_violation"
        assert data["status"] == "open"


# =========================================================================
# SessionLog Unit Tests
# =========================================================================

class TestSessionLog:
    """Tests for SessionLog model."""

    def test_session_log_creation(self, db_session):
        """SessionLog creates with required fields."""
        session = SessionLog(
            session_id="ws-session-123",
            session_type="websocket",
            actor_type="user",
            actor_id="user-001",
            agentium_id="SESS00001",
        )
        db_session.add(session)
        db_session.commit()

        assert session.session_id == "ws-session-123"
        assert session.session_type == "websocket"
        assert session.actor_type == "user"
        assert session.actor_id == "user-001"
        assert session.started_at is not None
        assert session.termination_reason is None

    def test_session_record_activity(self, db_session):
        """record_activity updates last_activity_at."""
        session = SessionLog(
            session_id="activity-test",
            session_type="http",
            actor_type="agent",
            actor_id="30001",
            agentium_id="SESS00002",
        )
        db_session.add(session)
        db_session.commit()

        original_activity = session.last_activity_at
        import time
        time.sleep(0.01)
        session.record_activity()
        db_session.commit()

        assert session.last_activity_at > original_activity

    def test_session_end_session(self, db_session):
        """end_session marks session as ended."""
        session = SessionLog(
            session_id="end-test",
            session_type="websocket",
            actor_type="user",
            actor_id="user-001",
            agentium_id="SESS00003",
        )
        db_session.add(session)
        db_session.commit()

        session.end_session("timeout")
        db_session.commit()

        assert session.ended_at is not None
        assert session.termination_reason == "timeout"

    def test_session_is_active(self, db_session):
        """is_active checks timeout correctly."""
        session = SessionLog(
            session_id="active-test",
            session_type="http",
            actor_type="user",
            actor_id="user-002",
            agentium_id="SESS00004",
        )
        db_session.add(session)
        db_session.commit()

        # Should be active (just created)
        assert session.is_active(timeout_seconds=3600) is True

        # Simulate old activity
        session.last_activity_at = datetime.utcnow() - timedelta(seconds=7200)
        db_session.commit()

        # Should be inactive with 1 hour timeout
        assert session.is_active(timeout_seconds=3600) is False
        # But active with 3 hour timeout
        assert session.is_active(timeout_seconds=10800) is True

    def test_session_add_audit(self, db_session):
        """add_audit links audit entry and increments counter."""
        session = SessionLog(
            session_id="audit-link",
            session_type="internal",
            actor_type="system",
            actor_id="SYSTEM",
            agentium_id="SESS00005",
        )
        db_session.add(session)
        db_session.commit()

        audit = AuditLog(
            level=AuditLevel.INFO,
            category=AuditCategory.SYSTEM,
            actor_type="system",
            actor_id="SYSTEM",
            action="test_action",
        )
        db_session.add(audit)
        db_session.commit()

        session.add_audit(audit)
        db_session.commit()

        assert audit.session_id == "audit-link"
        assert session.requests_count == 1

    def test_session_to_dict(self, db_session):
        """to_dict includes all fields."""
        session = SessionLog(
            session_id="dict-session",
            session_type="websocket",
            actor_type="user",
            actor_id="user-dict",
            agentium_id="SESS00006",
        )
        db_session.add(session)
        db_session.commit()

        data = session.to_dict()

        assert data["session_id"] == "dict-session"
        assert data["actor"] == "user-dict"
        assert data["type"] == "websocket"
        assert data["status"] == "active"


# =========================================================================
# HealthCheck Unit Tests
# =========================================================================

class TestHealthCheck:
    """Tests for HealthCheck model."""

    def test_health_check_creation(self, db_session):
        """HealthCheck creates with required fields."""
        health = HealthCheck(
            component="database",
            status="healthy",
            latency_ms=5,
            error_rate=0.0,
            memory_usage_mb=256,
            cpu_usage_percent=15.5,
            active_connections=10,
        )
        db_session.add(health)
        db_session.commit()

        assert health.component == "database"
        assert health.status == "healthy"
        assert health.latency_ms == 5
        assert health.error_rate == 0.0
        assert health.is_healthy() is True

    def test_health_check_unhealthy(self, db_session):
        """is_healthy returns False for unhealthy."""
        health = HealthCheck(
            component="redis",
            status="degraded",
            latency_ms=500,
            error_rate=0.15,
        )
        db_session.add(health)
        db_session.commit()

        assert health.is_healthy() is False

    def test_health_check_to_dict(self, db_session):
        """to_dict includes all metrics."""
        health = HealthCheck(
            component="api_gateway",
            status="healthy",
            latency_ms=10,
            error_rate=0.01,
            active_connections=100,
        )
        db_session.add(health)
        db_session.commit()

        data = health.to_dict()

        assert data["component"] == "api_gateway"
        assert data["status"] == "healthy"
        assert data["metrics"]["latency_ms"] == 10
        assert data["metrics"]["error_rate"] == 0.01
        assert data["metrics"]["connections"] == 100


# =========================================================================
# Cross-Model Integration Tests
# =========================================================================

class TestUserAuditIntegration:
    """Integration tests between User, Audit, and Preference models."""

    def test_user_with_audit_logs(self, db_session):
        """User actions create audit logs."""
        user = User(
            username="audited",
            email="audited@example.com",
            hashed_password=User.hash_password("pass"),
        )
        db_session.add(user)
        db_session.commit()

        # Create audit log for user action
        audit = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.AUTHENTICATION,
            actor_type="user",
            actor_id=user.id,
            action="login",
            description=f"User {user.username} logged in",
            success=True,
        )
        db_session.add(audit)
        db_session.commit()

        assert audit.actor_id == user.id
        assert audit.category == AuditCategory.AUTHENTICATION

    def test_user_with_preferences(self, db_session):
        """User can have multiple preferences."""
        user = User(
            username="prefowner",
            email="prefowner@example.com",
            hashed_password=User.hash_password("pass"),
        )
        db_session.add(user)
        db_session.commit()

        prefs = [
            UserPreference(user_id=user.id, category=PreferenceCategory.UI, key="theme", value_json=json.dumps("dark"), agentium_id="UPF90001"),
            UserPreference(user_id=user.id, category=PreferenceCategory.NOTIFICATIONS, key="email", value_json=json.dumps(True), agentium_id="UPF90002"),
            UserPreference(user_id=user.id, category=PreferenceCategory.CHAT, key="history_limit", value_json=json.dumps(100), agentium_id="UPF90003"),
        ]
        db_session.add_all(prefs)
        db_session.commit()

        assert len(prefs) == 3
        assert all(p.user_id == user.id for p in prefs)

    def test_model_config_with_user(self, db_session):
        """UserModelConfig links to user."""
        user = User(
            username="configowner",
            email="configowner@example.com",
            hashed_password=User.hash_password("pass"),
        )
        db_session.add(user)
        db_session.commit()

        config = UserModelConfig(
            provider=ProviderType.OPENAI,
            config_name="Personal Config",
            default_model="gpt-4",
            user_id=user.id,
            is_default=True,
        )
        db_session.add(config)
        db_session.commit()

        assert config.user_id == user.id
        assert config.is_default is True

    def test_audit_log_with_correlation(self, db_session):
        """Audit logs can be correlated."""
        # Parent action
        parent = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.TASK,
            actor_type="agent",
            actor_id="10001",
            action="task_created",
            correlation_id="corr-123",
        )
        db_session.add(parent)
        db_session.commit()

        # Child actions
        for i in range(3):
            child = AuditLog.log(
                level=AuditLevel.INFO,
                category=AuditCategory.TASK,
                actor_type="agent",
                actor_id="30001",
                action=f"subtask_{i}_started",
                correlation_id="corr-123",
            )
            db_session.add(child)
        db_session.commit()

        # All have same correlation_id
        children = db_session.query(AuditLog).filter(
            AuditLog.correlation_id == "corr-123",
            AuditLog.id != parent.id
        ).all()
        assert len(children) == 3
        assert all(c.correlation_id == "corr-123" for c in children)
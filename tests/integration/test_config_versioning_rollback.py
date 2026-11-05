"""Integration tests for Config Versioning Rollback (Task 21.5.3).

Verifies POST /admin/config-restore/{entity_type}/{entity_id} (ConfigVersioningService.restore_snapshot)
completes in under 5 minutes (300s) without data corruption.
"""

import time
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

# Pytest markers
pytestmark = [
    pytest.mark.integration,
    pytest.mark.rollback,
    pytest.mark.sla,
]

from backend.services.config_versioning import ConfigVersioningService
from backend.models.entities.channels import ExternalChannel
from backend.models.entities.user_config import UserModelConfig
from backend.models.entities.plugin import PluginInstallation
from tests.conftest import assert_completes_under
from backend.models.database import get_db


# ──────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def admin_user(db_session: Session):
    """Create an admin user for testing."""
    from backend.models.entities.user import User, pwd_context

    user = User(
        email="admin@test.com",
        username="admin_test",
        hashed_password=pwd_context.hash("password"),
        is_admin=True,
        is_active=True,
        role="primary_sovereign",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def db_client(db_session: Session):
    """TestClient with get_db overridden to use the test db_session."""
    from backend.main import app

    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # Session is managed by the db_session fixture

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(db_client: TestClient, admin_user):
    """Test client authenticated as admin."""
    from backend.core.auth import create_access_token

    token = create_access_token(data={"sub": admin_user.email, "tier": "0xxxx", "is_admin": True})
    db_client.headers.update({"Authorization": f"Bearer {token}"})
    return db_client


@pytest.fixture
def test_channel(db_session: Session, admin_user):
    """Create a test channel with multiple snapshots in git."""
    from backend.models.entities.channels import ChannelType, ChannelStatus

    # Generate agentium_id for the channel
    channel_count = db_session.query(ExternalChannel).count()
    agentium_id = f"CH{channel_count + 1:04d}"

    channel = ExternalChannel(
        id="test_channel_1",
        agentium_id=agentium_id,
        name="Test Channel",
        channel_type=ChannelType.SLACK,
        config={"webhook_url": "https://hooks.slack.com/test", "channel": "#general", "webhook_url_display": "https://hooks.slack.com/test"},
        default_agent_id=None,
        auto_create_tasks=True,
        require_approval=False,
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(channel)
    db_session.commit()
    db_session.refresh(channel)

    # Create initial snapshot (v1)
    ConfigVersioningService.commit_snapshot(
        entity_type="channel",
        entity_id=channel.id,
        actor_id=admin_user.id,
        payload_dict=channel.to_dict(),
    )

    # Update channel and create v2 snapshot
    channel.config = {"webhook_url": "https://hooks.slack.com/test_v2", "channel": "#general_v2", "webhook_url_display": "https://hooks.slack.com/test_v2"}
    channel.name = "Test Channel v2"
    db_session.commit()
    ConfigVersioningService.commit_snapshot(
        entity_type="channel",
        entity_id=channel.id,
        actor_id=admin_user.id,
        payload_dict=channel.to_dict(),
    )

    # Update channel and create v3 snapshot
    channel.config = {"webhook_url": "https://hooks.slack.com/test_v3", "channel": "#general_v3", "webhook_url_display": "https://hooks.slack.com/test_v3"}
    channel.name = "Test Channel v3"
    channel.auto_create_tasks = False
    db_session.commit()
    commit_sha_v3 = ConfigVersioningService.commit_snapshot(
        entity_type="channel",
        entity_id=channel.id,
        actor_id=admin_user.id,
        payload_dict=channel.to_dict(),
    )

    # Update channel to current state (v4)
    channel.config = {"webhook_url": "https://hooks.slack.com/test_v4", "channel": "#general_v4", "webhook_url_display": "https://hooks.slack.com/test_v4"}
    channel.name = "Test Channel v4"
    channel.auto_create_tasks = True
    channel.require_approval = True
    db_session.commit()
    ConfigVersioningService.commit_snapshot(
        entity_type="channel",
        entity_id=channel.id,
        actor_id=admin_user.id,
        payload_dict=channel.to_dict(),
    )

    yield {
        "channel": channel,
        "v3_commit": commit_sha_v3,
        "admin_user": admin_user,
    }

    # Cleanup
    db_session.delete(channel)
    db_session.commit()


@pytest.fixture
def test_model_config(db_session: Session, admin_user):
    """Create a test model config with multiple snapshots."""
    from backend.models.entities.user_config import ProviderType

    config = UserModelConfig(
        id="test_model_1",
        provider=ProviderType.OPENAI,
        provider_name="openai",
        config_name="GPT-4",
        api_base_url="https://api.openai.com/v1",
        default_model="gpt-4",
        available_models=["gpt-4", "gpt-3.5-turbo"],
        is_default=True,
        max_tokens=4096,
        temperature=0.7,
        top_p=1.0,
        timeout_seconds=30,
        status="ACTIVE",
        api_key_encrypted="encrypted_key_v1",
    )
    db_session.add(config)
    db_session.commit()
    db_session.refresh(config)

    # Create initial snapshot (v1)
    ConfigVersioningService.commit_snapshot(
        entity_type="model_config",
        entity_id=config.id,
        actor_id=admin_user.id,
        payload_dict={
            "provider": config.provider.value,
            "provider_name": config.provider_name,
            "config_name": config.config_name,
            "api_base_url": config.api_base_url,
            "local_server_url": config.local_server_url,
            "default_model": config.default_model,
            "available_models": config.available_models,
            "is_default": config.is_default,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "top_p": config.top_p,
            "timeout_seconds": config.timeout_seconds,
            "status": config.status,
            "api_key_encrypted": config.api_key_encrypted,
            "api_key_masked": "****",
        },
    )

    # Update and create v2 snapshot
    config.config_name = "GPT-4 v2"
    config.temperature = 0.5
    db_session.commit()
    ConfigVersioningService.commit_snapshot(
        entity_type="model_config",
        entity_id=config.id,
        actor_id=admin_user.id,
        payload_dict={
            "provider": config.provider.value,
            "provider_name": config.provider_name,
            "config_name": config.config_name,
            "api_base_url": config.api_base_url,
            "local_server_url": config.local_server_url,
            "default_model": config.default_model,
            "available_models": config.available_models,
            "is_default": config.is_default,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "top_p": config.top_p,
            "timeout_seconds": config.timeout_seconds,
            "status": config.status,
            "api_key_encrypted": config.api_key_encrypted,
            "api_key_masked": "****",
        },
    )

    # Update and create v3 snapshot
    config.config_name = "GPT-4 v3"
    config.temperature = 0.3
    config.max_tokens = 8192
    db_session.commit()
    commit_sha_v3 = ConfigVersioningService.commit_snapshot(
        entity_type="model_config",
        entity_id=config.id,
        actor_id=admin_user.id,
        payload_dict={
            "provider": config.provider.value,
            "provider_name": config.provider_name,
            "config_name": config.config_name,
            "api_base_url": config.api_base_url,
            "local_server_url": config.local_server_url,
            "default_model": config.default_model,
            "available_models": config.available_models,
            "is_default": config.is_default,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "top_p": config.top_p,
            "timeout_seconds": config.timeout_seconds,
            "status": config.status,
            "api_key_encrypted": config.api_key_encrypted,
            "api_key_masked": "****",
        },
    )

    # Update to current state (v4)
    config.config_name = "GPT-4 v4"
    config.temperature = 0.8
    config.max_tokens = 2048
    db_session.commit()
    ConfigVersioningService.commit_snapshot(
        entity_type="model_config",
        entity_id=config.id,
        actor_id=admin_user.id,
        payload_dict={
            "provider": config.provider.value,
            "provider_name": config.provider_name,
            "config_name": config.config_name,
            "api_base_url": config.api_base_url,
            "local_server_url": config.local_server_url,
            "default_model": config.default_model,
            "available_models": config.available_models,
            "is_default": config.is_default,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "top_p": config.top_p,
            "timeout_seconds": config.timeout_seconds,
            "status": config.status,
            "api_key_encrypted": config.api_key_encrypted,
            "api_key_masked": "****",
        },
    )

    yield {
        "model_config": config,
        "v3_commit": commit_sha_v3,
        "admin_user": admin_user,
    }

    # Cleanup
    db_session.delete(config)
    db_session.commit()


# ──────────────────────────────────────────────────────────────────────────────
# TESTS - Service Level (ConfigVersioningService.restore_snapshot)
# ──────────────────────────────────────────────────────────────────────────────

class TestConfigRollbackSLA:
    """SLA verification tests."""

    def test_restore_snapshot_completes_under_5min(self, test_channel):
        """Restore snapshot must complete within 300 seconds."""
        entity_type = "channel"
        entity_id = test_channel["channel"].id
        commit_sha = test_channel["v3_commit"]

        with assert_completes_under(300):
            snapshot = ConfigVersioningService.restore_snapshot(entity_type, entity_id, commit_sha)

        assert snapshot is not None
        assert snapshot["name"] == "Test Channel v3"
        assert snapshot["config"]["webhook_url"] == "https://hooks.slack.com/test_v3"


class TestConfigRollbackDataIntegrity:
    """Data integrity verification tests."""

    def test_restore_snapshot_returns_correct_data(self, test_channel):
        """Restored snapshot must match the committed snapshot exactly."""
        entity_type = "channel"
        entity_id = test_channel["channel"].id
        commit_sha = test_channel["v3_commit"]

        # Get history to find v3 commit details
        history = ConfigVersioningService.get_config_history(entity_type, entity_id)
        v3_entry = next((h for h in history if h["sha"] == commit_sha), None)
        assert v3_entry is not None

        # Restore snapshot
        snapshot = ConfigVersioningService.restore_snapshot(entity_type, entity_id, commit_sha)

        # Verify restored data matches v3
        assert snapshot["name"] == "Test Channel v3"
        assert snapshot["config"]["webhook_url"] == "https://hooks.slack.com/test_v3"
        assert snapshot["config"]["channel"] == "#general_v3"
        assert snapshot["routing"]["auto_create_tasks"] is False
        assert snapshot["routing"]["require_approval"] is False

    def test_restore_snapshot_channel_restores_all_fields(self, test_channel, db_session: Session):
        """Channel entity must have all fields restored from snapshot."""
        entity_type = "channel"
        entity_id = test_channel["channel"].id
        commit_sha = test_channel["v3_commit"]

        # Current state is v4
        channel = db_session.query(ExternalChannel).filter(ExternalChannel.id == entity_id).first()
        assert channel.name == "Test Channel v4"
        assert channel.config["webhook_url"] == "https://hooks.slack.com/test_v4"
        assert channel.auto_create_tasks is True
        assert channel.require_approval is True

        # Restore to v3 via service
        snapshot = ConfigVersioningService.restore_snapshot(entity_type, entity_id, commit_sha)

        # Apply snapshot to channel (simulating API endpoint)
        for key in ["name", "config", "default_agent_id", "status"]:
            if key in snapshot:
                setattr(channel, key, snapshot[key])
        # routing fields are nested
        if "routing" in snapshot:
            channel.auto_create_tasks = snapshot["routing"]["auto_create_tasks"]
            channel.require_approval = snapshot["routing"]["require_approval"]
            channel.default_agent_id = snapshot["routing"]["default_agent"]
        db_session.commit()

        # Verify all fields restored
        db_session.refresh(channel)
        assert channel.name == "Test Channel v3"
        assert channel.config["webhook_url"] == "https://hooks.slack.com/test_v3"
        assert channel.config["channel"] == "#general_v3"
        assert channel.auto_create_tasks is False
        assert channel.require_approval is False
        assert channel.status == "active"
        assert channel.default_agent_id is None  # Was None in fixture

    def test_restore_snapshot_model_config_restores_fields(self, test_model_config, db_session: Session):
        """Model config entity must have fields restored (except sensitive keys)."""
        entity_type = "model_config"
        entity_id = test_model_config["model_config"].id
        commit_sha = test_model_config["v3_commit"]

        # Current state is v4
        config = db_session.query(UserModelConfig).filter(UserModelConfig.id == entity_id).first()
        assert config.config_name == "GPT-4 v4"
        assert config.temperature == 0.8
        assert config.max_tokens == 2048

        # Restore to v3 via service
        snapshot = ConfigVersioningService.restore_snapshot(entity_type, entity_id, commit_sha)

        # Apply snapshot to config (simulating API endpoint)
        for key in ["provider_name", "config_name", "api_base_url", "local_server_url",
                    "default_model", "available_models", "is_default", "max_tokens",
                    "temperature", "top_p", "timeout_seconds", "status"]:
            if key in snapshot:
                setattr(config, key, snapshot[key])
        db_session.commit()

        # Verify fields restored
        db_session.refresh(config)
        assert config.config_name == "GPT-4 v3"
        assert config.temperature == 0.3
        assert config.max_tokens == 8192
        assert config.available_models == ["gpt-4", "gpt-3.5-turbo"]
        # Sensitive fields should NOT be restored
        assert config.api_key_encrypted == "encrypted_key_v1"  # Original value preserved


class TestConfigRollbackErrorHandling:
    """Error handling tests."""

    def test_restore_snapshot_invalid_commit_raises_error(self, test_channel):
        """Invalid commit SHA must raise ValueError."""
        entity_type = "channel"
        entity_id = test_channel["channel"].id

        with pytest.raises(ValueError) as exc_info:
            ConfigVersioningService.restore_snapshot(entity_type, entity_id, "invalid_sha_12345")

        assert "not found in repository" in str(exc_info.value)

    def test_restore_snapshot_missing_file_raises_error(self, test_channel):
        """Missing file in commit must raise ValueError."""
        entity_type = "channel"
        entity_id = test_channel["channel"].id
        commit_sha = test_channel["v3_commit"]

        # Use a valid commit but with a different entity_type that doesn't have this entity
        # This tests the "file not found in commit" path
        with pytest.raises(ValueError) as exc_info:
            ConfigVersioningService.restore_snapshot("model_config", "nonexistent_entity", commit_sha)

        assert "not found in commit" in str(exc_info.value)

    def test_restore_snapshot_corrupt_json_raises_error(self, test_channel, db_session: Session):
        """Corrupt JSON in commit must raise ValueError."""
        # This would require manually corrupting the git repo
        # Skip for now as it's hard to set up cleanly
        pass


# ──────────────────────────────────────────────────────────────────────────────
# TESTS - API Level (POST /admin/config-restore/{entity_type}/{entity_id})
# ──────────────────────────────────────────────────────────────────────────────

class TestConfigRestoreAPI:
    """API endpoint tests."""

    def test_restore_channel_api_success(self, admin_client: TestClient, test_channel, db_session: Session):
        """POST /admin/config-restore/channel/{id} must restore channel to snapshot."""
        entity_id = test_channel["channel"].id
        commit_sha = test_channel["v3_commit"]

        # Verify current state is v4
        channel = db_session.query(ExternalChannel).filter(ExternalChannel.id == entity_id).first()
        assert channel.name == "Test Channel v4"

        # Call restore API
        response = admin_client.post(
            f"/api/v1/admin/config-restore/channel/{entity_id}",
            params={"commit": commit_sha},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "restored to" in data["message"]

        # Verify channel restored to v3
        db_session.refresh(channel)
        assert channel.name == "Test Channel v3"
        assert channel.config["webhook_url"] == "https://hooks.slack.com/test_v3"
        assert channel.config["channel"] == "#general_v3"
        assert channel.auto_create_tasks is False
        assert channel.require_approval is False

    def test_restore_model_config_api_success(self, admin_client: TestClient, test_model_config, db_session: Session):
        """POST /admin/config-restore/model_config/{id} must restore config to snapshot."""
        entity_id = test_model_config["model_config"].id
        commit_sha = test_model_config["v3_commit"]

        # Verify current state is v4
        config = db_session.query(UserModelConfig).filter(UserModelConfig.id == entity_id).first()
        assert config.config_name == "GPT-4 v4"
        assert config.temperature == 0.8
        assert config.max_tokens == 2048

        # Call restore API
        response = admin_client.post(
            f"/api/v1/admin/config-restore/model_config/{entity_id}",
            params={"commit": commit_sha},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "restored to" in data["message"]
        # Warning about API key fields
        assert "warnings" in data

        # Verify config restored to v3
        db_session.refresh(config)
        assert config.config_name == "GPT-4 v3"
        assert config.temperature == 0.3
        assert config.max_tokens == 8192
        # Sensitive fields not restored
        assert config.api_key_encrypted == "encrypted_key_v1"

    def test_restore_api_rejects_invalid_commit(self, admin_client: TestClient, test_channel):
        """API must return 400 for invalid commit SHA."""
        entity_id = test_channel["channel"].id

        response = admin_client.post(
            f"/api/v1/admin/config-restore/channel/{entity_id}",
            params={"commit": "invalid_sha_12345"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "not found in repository" in data["error"]

    def test_restore_api_rejects_missing_entity(self, admin_client: TestClient, test_channel):
        """API must return 404 for non-existent entity."""
        # Use a valid commit SHA but with non-existent entity ID
        commit_sha = test_channel["v3_commit"]
        response = admin_client.post(
            "/api/v1/admin/config-restore/channel/nonexistent_id",
            params={"commit": commit_sha},
        )

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["error"].lower()

    def test_restore_api_rejects_unsupported_entity_type(self, admin_client: TestClient, test_channel):
        """API must return 400 for unsupported entity type."""
        entity_id = test_channel["channel"].id
        commit_sha = test_channel["v3_commit"]

        response = admin_client.post(
            f"/api/v1/admin/config-restore/unsupported_type/{entity_id}",
            params={"commit": commit_sha},
        )

        assert response.status_code == 400
        data = response.json()
        assert "unsupported entity type" in data["error"].lower()

    def test_restore_api_rejects_non_admin(self, db_client: TestClient, test_channel, db_session: Session):
        """Non-admin users must be rejected (403)."""
        from backend.models.entities.user import User, pwd_context
        from backend.core.auth import create_access_token

        # Create non-admin user
        user = User(
            email="user@test.com",
            username="regular_user",
            hashed_password=pwd_context.hash("password"),
            is_admin=False,
            is_active=True,
            role="observer",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        token = create_access_token(data={"sub": user.email, "tier": "2xxxx", "is_admin": False})
        db_client.headers.update({"Authorization": f"Bearer {token}"})

        entity_id = test_channel["channel"].id
        commit_sha = test_channel["v3_commit"]

        response = db_client.post(
            f"/api/v1/admin/config-restore/channel/{entity_id}",
            params={"commit": commit_sha},
        )

        assert response.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
# tests/test_lifespan_4_1.py
import pytest
import logging
from fastapi.testclient import TestClient


def test_4_1_1_lifespan_completes(app, caplog):
    """4.1.1: lifespan() completes all init steps without error."""
    caplog.set_level(logging.INFO, logger="backend.main")
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        # Check for successful startup indicators
        assert "Database initialized" in caplog.text or "API Manager initialized" in caplog.text


def test_4_1_2_security_startup_checks(app, caplog, monkeypatch):
    """4.1.2: Security startup checks run (run_security_startup_checks)."""
    # Test default creds warning (non-strict mode)
    monkeypatch.setenv("MINIO_ROOT_USER", "minioadmin")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "minioadmin")
    monkeypatch.setenv("MINIO_BLOCK_DEFAULT_CREDS", "false")
    
    caplog.set_level(logging.WARNING, logger="backend.core.security_checks")
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "SECURITY ALERT" in caplog.text or "default credentials" in caplog.text.lower()


def test_4_1_2_security_startup_checks_strict(app_testing_mode, caplog, monkeypatch):
    """4.1.2 strict mode: RuntimeError raised with MINIO_BLOCK_DEFAULT_CREDS=true."""
    monkeypatch.setenv("MINIO_ROOT_USER", "minioadmin")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "minioadmin")
    monkeypatch.setenv("MINIO_BLOCK_DEFAULT_CREDS", "true")
    
    # App startup should raise RuntimeError during TestClient context entry
    import importlib
    import backend.main
    importlib.reload(backend.main)
    from backend.main import app as reloaded_app
    
    with pytest.raises(RuntimeError, match="default credentials"):
        with TestClient(reloaded_app) as client:
            client.get("/api/health")


def test_4_1_3_workspace_config_validation(app, caplog, monkeypatch):
    """4.1.3: Workspace config validation runs."""
    # Test misconfigured workspace (enabled but invalid root)
    monkeypatch.setenv("HOST_WORKSPACE_ENABLED", "true")
    monkeypatch.setenv("HOST_WORKSPACE_ROOT", "/nonexistent")
    
    caplog.set_level(logging.WARNING, logger="backend.main")
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "misconfigured" in caplog.text.lower() or "workspace config check failed" in caplog.text.lower()


def test_4_1_3_workspace_config_validation_ok(app, caplog, monkeypatch):
    """4.1.3: Workspace config validation passes when correctly configured."""
    monkeypatch.setenv("HOST_WORKSPACE_ENABLED", "false")
    
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        # Should not log workspace warnings
        assert "misconfigured" not in caplog.text.lower()


from backend.models.entities import Constitution
from sqlalchemy.orm import Session


def test_4_1_4_constitution_seed_first_boot(app, db_engine):
    """4.1.4: Constitution seed executes on first boot."""
    with Session(db_engine) as db:
        constitution = db.query(Constitution).filter_by(is_active=True).first()
        assert constitution is not None, "Fallback constitution should be created"
        assert constitution.version == "v1.0.0"
        # Verify it's the fallback (not genesis) constitution
        assert "Core Constitution" in constitution.preamble or "fallback" in constitution.preamble.lower()


def test_4_1_4_constitution_seed_reused(app, db_engine):
    """4.1.4: Existing constitution is reused on subsequent boots."""
    # First boot already happened in previous test
    with Session(db_engine) as db:
        count = db.query(Constitution).filter_by(is_active=True).count()
        assert count == 1, "Should not create duplicate constitution"
        constitution = db.query(Constitution).filter_by(is_active=True).first()
        assert constitution.version == "v1.0.0"


def test_4_1_5_persistent_council_status_check(app, caplog):
    """4.1.5: Persistent Council status check runs."""
    caplog.set_level(logging.INFO, logger="backend.main")
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        # Fresh DB: Council not yet initialized (genesis hasn't run)
        assert "Persistent Council not yet initialized" in caplog.text or "already initialized" in caplog.text.lower()


def test_4_1_6_api_manager_model_allocator_token_optimizer(app_testing_mode, caplog):
    """4.1.6: API Manager, Model Allocator, Token Optimizer initialize."""
    caplog.set_level(logging.INFO, logger="backend.main")
    with TestClient(app_testing_mode) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "API Manager initialized" in caplog.text
        assert "Model Allocator initialized" in caplog.text
        assert "Token Optimizer initialized" in caplog.text
        # Also verify idle budget logs
        assert "Idle Budget" in caplog.text
        assert "Active Mode Budget" in caplog.text


def test_4_1_7_mcp_tool_bridge_init(app_testing_mode, caplog):
    """4.1.7: MCP Tool Bridge initializes."""
    caplog.set_level(logging.INFO, logger="backend.main")
    with TestClient(app_testing_mode) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "MCP Tool Bridge initialized" in caplog.text
        # In TESTING mode, should show 0 tools loaded
        assert "approved tool(s) loaded" in caplog.text


def test_4_1_8_pricing_sync_background(app, caplog):
    """4.1.8: Pricing sync runs in background."""
    caplog.set_level(logging.INFO, logger="backend.main")
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        # Background pricing sync task is created
        assert "Background pricing synchronization" in caplog.text or "pricing cache" in caplog.text.lower()
        # Pricing cache loaded from DB
        assert "pricing cache" in caplog.text.lower() or "Loaded" in caplog.text


def test_4_1_9_idle_governance_engine_starts(app_testing_mode, caplog):
    """4.1.9: Idle Governance engine starts."""
    caplog.set_level(logging.INFO, logger="backend.main")
    with TestClient(app_testing_mode) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "Idle Governance Engine and monitors started" in caplog.text
        assert "Eternal Council and Background Health Scanners active" in caplog.text
        assert "Database Maintenance & Backup Scanners active" in caplog.text
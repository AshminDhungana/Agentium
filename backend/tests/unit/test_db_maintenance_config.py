from backend.core.config import get_settings


def test_db_maintenance_batch_settings_exist():
    s = get_settings()
    assert hasattr(s, "DB_MAINTENANCE_BATCH_SIZE")
    assert hasattr(s, "DB_MAINTENANCE_BATCH_SLEEP")
    assert s.DB_MAINTENANCE_BATCH_SIZE == 1000
    assert s.DB_MAINTENANCE_BATCH_SLEEP == 0.1


def test_db_maintenance_batch_settings_overridable(monkeypatch):
    monkeypatch.setenv("DB_MAINTENANCE_BATCH_SIZE", "500")
    monkeypatch.setenv("DB_MAINTENANCE_BATCH_SLEEP", "0.05")
    from backend.core.config import get_settings as get_settings_fresh
    get_settings_fresh.cache_clear()
    import backend.core.config as config_mod
    import importlib
    importlib.reload(config_mod)
    s = config_mod.get_settings()
    assert s.DB_MAINTENANCE_BATCH_SIZE == 500
    assert s.DB_MAINTENANCE_BATCH_SLEEP == 0.05
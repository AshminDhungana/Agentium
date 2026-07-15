from backend.core.config import get_settings


def test_pool_settings_have_production_defaults():
    s = get_settings()
    assert s.DATABASE_POOL_SIZE == 20
    assert s.DATABASE_MAX_OVERFLOW == 10
    assert s.DATABASE_POOL_TIMEOUT == 30
    assert s.DATABASE_POOL_RECYCLE == 1800


import importlib
import os

import backend.core.config as config_mod
import backend.models.database as db_mod
from sqlalchemy.pool import QueuePool


def _reload_db_with(overrides: dict):
    for k, v in overrides.items():
        os.environ[k] = str(v)
    config_mod.get_settings.cache_clear()
    importlib.reload(config_mod)
    return importlib.reload(db_mod)


def test_app_engine_honors_settings():
    reloaded = _reload_db_with({
        "DATABASE_POOL_SIZE": 15,
        "DATABASE_MAX_OVERFLOW": 5,
        "DATABASE_POOL_TIMEOUT": 12,
        "DATABASE_POOL_RECYCLE": 900,
    })
    pool = reloaded.engine.pool
    assert isinstance(pool, QueuePool)
    assert pool.size() == 15
    assert pool._max_overflow == 5
    assert pool._timeout == 12
    assert pool._recycle == 900
    assert pool._pre_ping is True
    for k in ("DATABASE_POOL_SIZE", "DATABASE_MAX_OVERFLOW",
              "DATABASE_POOL_TIMEOUT", "DATABASE_POOL_RECYCLE"):
        os.environ.pop(k, None)
    config_mod.get_settings.cache_clear()
    importlib.reload(config_mod)

from backend.core.config import get_settings


def test_pool_settings_have_production_defaults():
    s = get_settings()
    assert s.DATABASE_POOL_SIZE == 20
    assert s.DATABASE_MAX_OVERFLOW == 10
    assert s.DATABASE_POOL_TIMEOUT == 30
    assert s.DATABASE_POOL_RECYCLE == 1800

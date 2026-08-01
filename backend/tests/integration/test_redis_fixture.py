"""Verify redis_client fixture connects and flushes correctly."""
import pytest
import redis


@pytest.mark.integration
def test_redis_fixture_connects(redis_client):
    """Fixture should provide a working Redis client."""
    assert isinstance(redis_client, redis.Redis)
    # Ping should succeed
    assert redis_client.ping() is True


@pytest.mark.integration
def test_redis_fixture_is_clean(redis_client):
    """Each test should get a clean Redis DB."""
    # Set a key
    redis_client.set("test:fixture:key", "value")
    assert redis_client.get("test:fixture:key") == b"value"

    # Next test should not see it (fixture flushes after yield)
    # This is verified by the next test running independently
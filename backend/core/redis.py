import os
import redis.asyncio as aioredis

def get_redis_client():
    """
    Provides an asynchronous Redis client.
    Uses the REDIS_URL environment variable, defaulting to redis://redis:6379/0.
    """
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return aioredis.from_url(redis_url, decode_responses=True)

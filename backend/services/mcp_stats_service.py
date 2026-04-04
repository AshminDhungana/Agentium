"""
MCP Stats Service
================================
Standalone Redis-backed service for:
  - Per-tool invocation metrics (atomic, pipeline-safe)
  - Sub-second revocation via Redis SET
  - Live stats read with <50 ms target

Redis key layout
----------------
agentium:mcp:stats:{tool_id}   → Hash
    invocation_count   int
    error_count        int
    total_latency_ms   float    (used to compute rolling avg)
    last_used_ts       float    (unix timestamp)

agentium:mcp:revoked           → SET of tool_id strings (no TTL)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Key constants ──────────────────────────────────────────────────────────────
_STATS_PREFIX   = "agentium:mcp:stats:"
_REVOKED_KEY    = "agentium:mcp:revoked"
_STATS_INDEX    = "agentium:mcp:tools_with_stats"   # SET of tool_ids that have stats
_STATS_TTL      = 86_400 * 7                         # 7-day rolling TTL (refreshed on write)


def _get_redis():
    """
    Return a Redis client.  Raises ``RuntimeError`` if Redis is unavailable.
    Callers should catch and degrade gracefully.
    """
    try:
        import redis as _redis
        url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        client = _redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=2,
        )
        client.ping()
        return client
    except Exception as exc:
        raise RuntimeError(f"Redis unavailable: {exc}") from exc


# ── Stats recording ────────────────────────────────────────────────────────────

def record_invocation(
    tool_id: str,
    latency_ms: float,
    success: bool,
) -> None:
    """
    Atomically record one tool invocation in Redis.

    Uses a pipeline (not a Lua script) for simplicity; the rolling-average
    is computed lazily on read so no WATCH/multi-exec is needed here.

    Args:
        tool_id:    The tool's DB UUID string.
        latency_ms: Wall-clock time of the invocation in milliseconds.
        success:    Whether the invocation succeeded.
    """
    try:
        r = _get_redis()
        key = f"{_STATS_PREFIX}{tool_id}"

        pipe = r.pipeline(transaction=False)
        pipe.hincrbyfloat(key, "invocation_count", 1)
        pipe.hincrbyfloat(key, "total_latency_ms", max(0.0, latency_ms))
        if not success:
            pipe.hincrbyfloat(key, "error_count", 1)
        pipe.hset(key, "last_used_ts", time.time())
        pipe.expire(key, _STATS_TTL)
        # Track which tool_ids have stats so we can SCAN efficiently
        pipe.sadd(_STATS_INDEX, tool_id)
        pipe.execute()
    except Exception as exc:
        # Non-fatal — stats are best-effort
        logger.debug("[MCPStats] record_invocation failed for %s: %s", tool_id, exc)


# ── Stats reading ──────────────────────────────────────────────────────────────

def _parse_stats(tool_id: str, raw: Dict[str, str]) -> Dict[str, Any]:
    """Convert raw Redis hash strings into a typed stats dict."""
    invocations    = int(float(raw.get("invocation_count", 0)))
    errors         = int(float(raw.get("error_count", 0)))
    total_latency  = float(raw.get("total_latency_ms", 0.0))
    last_used_ts   = float(raw.get("last_used_ts", 0.0))

    avg_latency = (total_latency / invocations) if invocations > 0 else 0.0
    error_rate  = (errors / invocations) if invocations > 0 else 0.0

    return {
        "tool_id":          tool_id,
        "invocation_count": invocations,
        "error_count":      errors,
        "avg_latency_ms":   round(avg_latency, 2),
        "error_rate":       round(error_rate, 4),   # 0.0 – 1.0
        "last_used_ts":     last_used_ts,
    }


def get_tool_stats(tool_id: str) -> Optional[Dict[str, Any]]:
    """
    Return live stats for a single tool, or ``None`` if no data exists.
    Always reads from Redis — no DB query.
    """
    try:
        r   = _get_redis()
        raw = r.hgetall(f"{_STATS_PREFIX}{tool_id}")
        if not raw:
            return None
        return _parse_stats(tool_id, raw)
    except Exception as exc:
        logger.debug("[MCPStats] get_tool_stats failed for %s: %s", tool_id, exc)
        return None


def get_all_stats() -> List[Dict[str, Any]]:
    """
    Return live stats for every tool that has ever been invoked.
    Reads all keys in one round-trip (SMEMBERS + pipeline HGETALL).
    Target: <50 ms.
    """
    try:
        r = _get_redis()

        # Get all tool_ids with stats
        tool_ids = r.smembers(_STATS_INDEX)
        if not tool_ids:
            return []

        # Batch fetch all hashes in one pipeline
        pipe = r.pipeline(transaction=False)
        for tid in tool_ids:
            pipe.hgetall(f"{_STATS_PREFIX}{tid}")
        raw_results = pipe.execute()

        stats = []
        for tool_id, raw in zip(tool_ids, raw_results):
            if raw:
                stats.append(_parse_stats(tool_id, raw))

        return sorted(stats, key=lambda s: s["invocation_count"], reverse=True)
    except Exception as exc:
        logger.warning("[MCPStats] get_all_stats failed: %s", exc)
        return []


def get_stats_for_tools(tool_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Return a mapping of tool_id → stats for the given list.
    Used by the stats endpoint to enrich a known tool list.
    """
    if not tool_ids:
        return {}
    try:
        r    = _get_redis()
        pipe = r.pipeline(transaction=False)
        for tid in tool_ids:
            pipe.hgetall(f"{_STATS_PREFIX}{tid}")
        raw_results = pipe.execute()

        result = {}
        for tool_id, raw in zip(tool_ids, raw_results):
            if raw:
                result[tool_id] = _parse_stats(tool_id, raw)
        return result
    except Exception as exc:
        logger.warning("[MCPStats] get_stats_for_tools failed: %s", exc)
        return {}


# ── Revocation ─────────────────────────────────────────────────────────────────

def add_to_revoked(tool_id: str) -> bool:
    """
    Add ``tool_id`` to the Redis revocation SET.
    Returns True on success, False if Redis is unavailable.
    Sub-second propagation: any subsequent ``is_revoked()`` call returns True.
    """
    try:
        r = _get_redis()
        r.sadd(_REVOKED_KEY, tool_id)
        logger.info("[MCPStats] Tool %s added to revocation SET", tool_id)
        return True
    except Exception as exc:
        logger.error("[MCPStats] add_to_revoked failed for %s: %s", tool_id, exc)
        return False


def remove_from_revoked(tool_id: str) -> bool:
    """
    Remove ``tool_id`` from the Redis revocation SET (e.g. after re-approval).
    Returns True on success.
    """
    try:
        r = _get_redis()
        r.srem(_REVOKED_KEY, tool_id)
        logger.info("[MCPStats] Tool %s removed from revocation SET", tool_id)
        return True
    except Exception as exc:
        logger.error("[MCPStats] remove_from_revoked failed for %s: %s", tool_id, exc)
        return False


def is_revoked(tool_id: str) -> bool:
    """
    Return True if ``tool_id`` is in the Redis revocation SET.
    Falls back to False (fail-open) if Redis is unavailable — the DB-level
    status check in MCPGovernanceService is the authoritative fallback.
    """
    try:
        r = _get_redis()
        return bool(r.sismember(_REVOKED_KEY, tool_id))
    except Exception as exc:
        logger.debug("[MCPStats] is_revoked check failed for %s (fail-open): %s", tool_id, exc)
        return False


def get_revoked_ids() -> List[str]:
    """Return all currently revoked tool IDs from Redis."""
    try:
        r = _get_redis()
        return list(r.smembers(_REVOKED_KEY))
    except Exception as exc:
        logger.warning("[MCPStats] get_revoked_ids failed: %s", exc)
        return []


# ── Health ─────────────────────────────────────────────────────────────────────

def redis_health() -> Dict[str, Any]:
    """Return a simple health/connectivity dict for the stats layer."""
    try:
        r     = _get_redis()
        info  = r.info("server")
        count = r.scard(_STATS_INDEX)
        return {
            "status":           "healthy",
            "redis_version":    info.get("redis_version", "unknown"),
            "tools_with_stats": count,
        }
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}
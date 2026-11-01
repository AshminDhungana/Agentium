"""
Health check tasks with comprehensive degradation summary.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.celery_app import celery_app
from backend.models.database import SessionLocal
from backend.models.entities.agents import Agent, AgentStatus
from backend.models.entities.channels import ExternalChannel as Channel
from backend.models.entities.task import Task, TaskStatus, TaskType
from backend.core.config import settings

from backend.services.structured_logging import get_structured_logger
logger = get_structured_logger(__name__)


@celery_app.task(name="agentium.monitoring.health_checks.run_health_check")
def run_health_check() -> Dict[str, Any]:
    """
    Run comprehensive system health check with degradation summary.

    Returns detailed degradation status including:
    - circuit_breakers: LLM provider circuit breaker states
    - fallbacks: Active fallback status (storage, vector store, LLM)
    - database_pool: Connection pool utilization
    - redis_queue: Celery queue depth
    - agents: Stalled/crashed agent status
    - channels: Channel connectivity status
    - resources: CPU, memory, disk utilization
    - anomalies: Recent anomaly detection results
    - overall: Aggregated degradation level (healthy/degraded/critical)
    """
    logger.info("Running comprehensive health check with degradation summary")

    db = SessionLocal()
    now = datetime.utcnow()

    try:
        # ─── Circuit Breaker Status ─────────────────────────────────────────
        circuit_breakers = _get_circuit_breaker_status()

        # ─── Fallback Status ────────────────────────────────────────────────
        fallbacks = _get_fallback_status()

        # ─── Database Pool ──────────────────────────────────────────────────
        db_pool = _get_db_pool_status()

        # ─── Redis Queue ────────────────────────────────────────────────────
        redis_queue = _get_redis_queue_status()

        # ─── Agent Health ───────────────────────────────────────────────────
        agents = _get_agent_health_status(db, now)

        # ─── Channel Health ─────────────────────────────────────────────────
        channels = _get_channel_health_status(db)

        # ─── Resource Utilization ───────────────────────────────────────────
        resources = _get_resource_status()

        # ─── Anomaly Status ─────────────────────────────────────────────────
        anomalies = _get_anomaly_status(db, now)

        # ─── Overall Degradation Level ──────────────────────────────────────
        overall = _calculate_overall_degradation(
            circuit_breakers, fallbacks, db_pool, redis_queue,
            agents, channels, resources, anomalies
        )

        result = {
            "timestamp": now.isoformat(),
            "overall": overall,
            "circuit_breakers": circuit_breakers,
            "fallbacks": fallbacks,
            "database_pool": db_pool,
            "redis_queue": redis_queue,
            "agents": agents,
            "channels": channels,
            "resources": resources,
            "anomalies": anomalies
        }

        logger.info(f"Health check completed: {overall['level']} ({overall['message']})")
        return result

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "timestamp": now.isoformat(),
            "overall": {
                "level": "critical",
                "critical_issues": 1,
                "warnings": 0,
                "message": f"Health check error: {str(e)}"
            },
            "error": str(e)
        }
    finally:
        db.close()


def _get_circuit_breaker_status() -> Dict[str, Any]:
    """Get circuit breaker states for all LLM providers."""
    try:
        from backend.core.llm_client import LLMClient
        breakers = LLMClient._circuit_breakers
        return {
            "providers": [
                {
                    "name": name,
                    "state": breaker.state,
                    "consecutive_failures": breaker.consecutive_failures,
                    "total_success": breaker.total_success,
                    "total_failure": breaker.total_failure,
                    "last_failure": breaker.last_failure_at.isoformat() if breaker.last_failure_at else None,
                    "config_id": breaker._config_id
                }
                for name, breaker in breakers.items()
            ],
            "any_open": any(b.state == "open" for b in breakers.values())
        }
    except Exception as e:
        logger.debug(f"Could not get circuit breaker status: {e}")
        return {"providers": [], "any_open": False, "error": "circuit_breaker_unavailable"}


def _get_fallback_status() -> Dict[str, Any]:
    """Get active fallback status for storage, vector store, and LLM providers."""
    fallbacks = {
        "storage": {"active": False, "provider": "local", "reason": None},
        "vector_store": {"active": False, "provider": "persistent_client", "reason": None},
        "llm": {"active": False, "provider": None, "reason": None}
    }

    # Check storage fallback
    try:
        from backend.services.storage_service import storage_service
        if hasattr(storage_service, 'use_s3') and not storage_service.use_s3:
            fallbacks["storage"] = {
                "active": True,
                "provider": "local",
                "reason": "S3 credentials missing or unreachable"
            }
    except Exception:
        pass

    # Check vector store fallback
    try:
        from backend.services.vector_store import vector_store
        fallbacks["vector_store"] = {
            "active": True,
            "provider": "chromadb_persistent" if not getattr(vector_store, 'use_http', True) else "chromadb_http",
            "reason": "HTTP client unavailable" if not getattr(vector_store, 'use_http', True) else None
        }
    except Exception:
        pass

    # Check LLM fallback (circuit breaker open = fallback active)
    try:
        from backend.core.llm_client import LLMClient
        breakers = LLMClient._circuit_breakers
        open_breakers = [
            name for name, b in breakers.items()
            if b.state == "open"
        ]
        if open_breakers:
            fallbacks["llm"] = {
                "active": True,
                "provider": open_breakers[0],
                "reason": f"Circuit breaker OPEN for: {', '.join(open_breakers)}"
            }
    except Exception:
        pass

    return fallbacks


def _get_db_pool_status() -> Dict[str, Any]:
    """Get database connection pool status."""
    try:
        from backend.core.database import engine
        pool = engine.pool
        size = pool.size()
        checked_out = pool.checkedout()
        overflow = pool.overflow()

        utilization = checked_out / size if size > 0 else 0

        return {
            "size": size,
            "checked_out": checked_out,
            "overflow": overflow,
            "utilization_percent": round(utilization * 100, 1),
            "status": "critical" if utilization > 0.9 else "warning" if utilization > 0.7 else "healthy",
            "exhausted": checked_out >= size
        }
    except Exception as e:
        logger.debug(f"Could not get DB pool status: {e}")
        return {
            "size": 0, "checked_out": 0, "overflow": 0,
            "utilization_percent": 0, "status": "unknown", "exhausted": False,
            "error": str(e)
        }


def _get_redis_queue_status() -> Dict[str, Any]:
    """Get Redis/Celery queue depth."""
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL)
        depth = r.llen('celery')
        return {
            "depth": depth,
            "status": "critical" if depth > 1000 else "warning" if depth > 500 else "healthy",
            "threshold_warning": 500,
            "threshold_critical": 1000
        }
    except Exception as e:
        logger.debug(f"Could not get Redis queue status: {e}")
        return {"depth": 0, "status": "unknown", "error": str(e)}


def _get_agent_health_status(db: Session, now: datetime) -> Dict[str, Any]:
    """Get agent health status (stalled/crashed)."""
    stale_threshold = now - timedelta(minutes=2)
    critical_threshold = now - timedelta(minutes=10)

    agents = db.query(Agent).filter(
        Agent.status.in_([AgentStatus.ACTIVE, AgentStatus.IDLE_WORKING])
    ).all()

    stalled = []
    crashed = []
    healthy = 0

    for a in agents:
        if not a.last_heartbeat_at:
            crashed.append({
                "agentium_id": a.agentium_id,
                "name": a.name,
                "reason": "no_heartbeat"
            })
        elif a.last_heartbeat_at < critical_threshold:
            crashed.append({
                "agentium_id": a.agentium_id,
                "name": a.name,
                "last_heartbeat": a.last_heartbeat_at.isoformat(),
                "minutes_since": int((now - a.last_heartbeat_at).total_seconds() / 60)
            })
        elif a.last_heartbeat_at < stale_threshold:
            stalled.append({
                "agentium_id": a.agentium_id,
                "name": a.name,
                "last_heartbeat": a.last_heartbeat_at.isoformat(),
                "minutes_since": int((now - a.last_heartbeat_at).total_seconds() / 60)
            })
        else:
            healthy += 1

    return {
        "total": len(agents),
        "healthy": healthy,
        "stalled": len(stalled),
        "crashed": len(crashed),
        "stalled_agents": stalled,
        "crashed_agents": crashed,
        "status": "critical" if crashed else "warning" if stalled else "healthy"
    }


def _get_channel_health_status(db: Session) -> Dict[str, Any]:
    """Get channel connectivity status."""
    channels = db.query(Channel).filter(Channel.is_active == True).all()
    results = []

    for ch in channels:
        try:
            from backend.services.idle_tasks.health_monitor import _send_channel_health_check
            import asyncio
            response = asyncio.run(asyncio.wait_for(
                _send_channel_health_check(ch.name, {'health_check': True}, timeout=5),
                timeout=10
            ))
            healthy = response.get('status') == 'ok'
            error = None
        except asyncio.TimeoutError:
            healthy = False
            error = "timeout"
        except Exception as e:
            healthy = False
            error = str(e)

        results.append({
            "name": ch.name,
            "type": ch.channel_type,
            "healthy": healthy,
            "error": error
        })

    unhealthy = [r for r in results if not r['healthy']]

    return {
        "total": len(channels),
        "healthy": len(channels) - len(unhealthy),
        "unhealthy": len(unhealthy),
        "details": results,
        "status": "critical" if unhealthy else "healthy"
    }


def _get_resource_status() -> Dict[str, Any]:
    """Get system resource utilization."""
    try:
        import psutil
        import sys

        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/' if sys.platform != 'win32' else 'C:\\')

        warnings = []
        if cpu_percent > 80:
            warnings.append(f"CPU at {cpu_percent:.1f}%")
        if memory.percent > 80:
            warnings.append(f"Memory at {memory.percent:.1f}%")
        if disk.percent > 80:
            warnings.append(f"Disk at {disk.percent:.1f}%")

        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent,
            "warnings": warnings,
            "status": "critical" if any(w for w in warnings if float(w.split()[-1].rstrip('%')) > 90) else "warning" if warnings else "healthy"
        }
    except Exception as e:
        logger.debug(f"Could not get resource status: {e}")
        return {"cpu_percent": 0, "memory_percent": 0, "disk_percent": 0, "warnings": [], "status": "unknown", "error": str(e)}


def _get_anomaly_status(db: Session, now: datetime) -> Dict[str, Any]:
    """Get recent anomaly detection status."""
    try:
        from sklearn.ensemble import IsolationForest
        import numpy as np

        since = now - timedelta(hours=2)
        tasks = db.query(Task).filter(Task.created_at >= since).all()

        if len(tasks) < 10:
            return {"status": "insufficient_data", "analyzed": len(tasks), "anomalies_found": 0}

        X = []
        task_refs = []
        for t in tasks:
            duration = (t.completed_at - t.created_at).total_seconds() if t.completed_at else 0
            tokens = t.tokens_used or 0
            agent_hash = hash(t.assigned_agent_id or '') % 1000
            type_hash = hash(t.task_type.value if t.task_type else '') % 100
            X.append([duration, tokens, agent_hash, type_hash])
            task_refs.append(t.id)

        X = np.array(X)
        iso_forest = IsolationForest(contamination=0.1, random_state=42)
        predictions = iso_forest.fit_predict(X)

        anomalies = []
        for i, pred in enumerate(predictions):
            if pred == -1:
                t = db.query(Task).filter_by(id=task_refs[i]).first()
                if t:
                    anomalies.append({
                        "task_id": t.id,
                        "task_type": t.task_type.value if t.task_type else 'unknown',
                        "agent_id": t.assigned_agent_id,
                        "duration_seconds": X[i][0],
                        "tokens": X[i][1]
                    })

        return {
            "status": "completed",
            "analyzed": len(tasks),
            "anomalies_found": len(anomalies),
            "anomalies": anomalies[:10]
        }
    except ImportError:
        return {"status": "skipped", "reason": "sklearn_not_installed"}
    except Exception as e:
        logger.debug(f"Could not get anomaly status: {e}")
        return {"status": "error", "error": str(e)}


def _calculate_overall_degradation(
    circuit_breakers: Dict,
    fallbacks: Dict,
    db_pool: Dict,
    redis_queue: Dict,
    agents: Dict,
    channels: Dict,
    resources: Dict,
    anomalies: Dict
) -> Dict[str, Any]:
    """Calculate overall degradation level."""
    critical_count = 0
    warning_count = 0

    # Circuit breakers
    if circuit_breakers.get("any_open"):
        critical_count += 1

    # Fallbacks
    active_fallbacks = sum(1 for f in fallbacks.values() if f.get("active"))
    if active_fallbacks > 0:
        warning_count += 1

    # DB pool
    if db_pool.get("status") == "critical":
        critical_count += 1
    elif db_pool.get("status") == "warning":
        warning_count += 1

    # Redis queue
    if redis_queue.get("status") == "critical":
        critical_count += 1
    elif redis_queue.get("status") == "warning":
        warning_count += 1

    # Agents
    if agents.get("status") == "critical":
        critical_count += 1
    elif agents.get("status") == "warning":
        warning_count += 1

    # Channels
    if channels.get("status") == "critical":
        critical_count += 1

    # Resources
    if resources.get("status") == "critical":
        critical_count += 1
    elif resources.get("status") == "warning":
        warning_count += 1

    if critical_count > 0:
        level = "critical"
    elif warning_count > 0:
        level = "degraded"
    else:
        level = "healthy"

    return {
        "level": level,
        "critical_issues": critical_count,
        "warnings": warning_count,
        "message": {
            "healthy": "All systems operational",
            "degraded": f"System degraded - {warning_count} warning(s)",
            "critical": f"System critical - {critical_count} critical issue(s)"
        }[level]
    }
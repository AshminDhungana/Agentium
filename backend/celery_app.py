"""
Celery configuration for Agentium background tasks.
Updated with Task Execution Architecture: Governance Alignment

"""
import os
import json
import time
import hmac
import hashlib
import logging

from celery import Celery
from celery.signals import worker_ready

os.environ.setdefault('PYTHONPATH', '/app')

logger = logging.getLogger(__name__)

celery_app = Celery(
    'agentium',
    broker=os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0'),
    backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0'),
    include=[
        'backend.services.tasks.task_executor',
        'backend.services.tasks.workflow_tasks',   # Workflow engine (006_workflow)
    ]
)

# ── Configuration ─────────────────────────────────────────────────────────────
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    beat_schedule_filename='/tmp/celerybeat-schedule',
    beat_scheduler='celery.beat.PersistentScheduler',
    broker_connection_retry_on_startup=True,
)

# ── Beat schedule ─────────────────────────────────────────────────────────────
celery_app.conf.beat_schedule = {
    # ── Channel health ────────────────────────────────────────────────────────
    'health-check-every-5-minutes': {
        'task': 'backend.services.tasks.task_executor.check_channel_health',
        'schedule': 300.0,
    },
    'cleanup-old-messages-daily': {
        'task': 'backend.services.tasks.task_executor.cleanup_old_channel_messages',
        'schedule': 86400.0,
        'kwargs': {'days': 30},
    },
    'imap-receiver-check': {
        'task': 'backend.services.tasks.task_executor.start_imap_receivers',
        'schedule': 60.0,
    },
    'channel-heartbeat': {
        'task': 'backend.services.tasks.task_executor.send_channel_heartbeat',
        'schedule': 300.0,
    },

    # ── Constitution & governance ─────────────────────────────────────────────
    'constitution-daily-review': {
        'task': 'backend.services.tasks.task_executor.daily_constitution_review',
        'schedule': 86400.0,
    },
    'idle-task-processor': {
        'task': 'backend.services.tasks.task_executor.process_idle_tasks',
        'schedule': 60.0,
    },

    # ── Task execution ────────────────────────────────────────────────────────
    'handle-task-escalation': {
        'task': 'backend.services.tasks.task_executor.handle_task_escalation',
        'schedule': 300.0,
    },
    'sovereign-data-retention': {
        'task': 'backend.services.tasks.task_executor.sovereign_data_retention',
        'schedule': 86400.0,
    },
    'auto-scale-check': {
        'task': 'backend.services.tasks.task_executor.auto_scale_check',
        'schedule': 600.0,
    },

    # ── Reasoning recovery watchdog (Gap 2) ───────────────────────────────────
    'reasoning-watchdog': {
        'task': 'backend.services.tasks.task_executor.check_stalled_reasoning',
        'schedule': 60.0,   # every 60 seconds
    },

    # ── Federation (Phase 11.2) ───────────────────────────────────────────────
    'federation-heartbeat': {
        'task': 'backend.celery_app.federation_heartbeat',
        'schedule': 300.0,   # every 5 minutes
    },
    'federation-cleanup-stale': {
        'task': 'backend.celery_app.federation_cleanup_stale',
        'schedule': 3600.0,  # every hour
    },

    # ── Phase 13.1: Auto-Delegation Engine ────────────────────────────────
    'auto-escalation-timer': {
        'task': 'backend.services.tasks.task_executor.check_escalation_timeouts',
        'schedule': 60.0,   # every 60 seconds
    },
    'dependency-graph-processor': {
        'task': 'backend.services.tasks.task_executor.process_dependency_graph',
        'schedule': 30.0,   # every 30 seconds
    },

    # ── Phase 13.2: Self-Healing & Auto-Recovery ──────────────────────────
    'agent-heartbeat': {
        'task': 'backend.services.tasks.task_executor.agent_heartbeat',
        'schedule': 60.0,   # every 60 seconds
    },
    'crash-detection': {
        'task': 'backend.services.tasks.task_executor.detect_crashed_agents',
        'schedule': 30.0,   # every 30 seconds
    },
    'self-diagnostic-daily': {
        'task': 'backend.services.tasks.task_executor.self_diagnostic_daily',
        'schedule': 86400.0,  # daily
    },
    'critical-path-guardian': {
        'task': 'backend.services.tasks.task_executor.critical_path_guardian',
        'schedule': 120.0,  # every 2 minutes
    },
    
    # ── Phase 13.3: Predictive Auto-Scaling ──────────────────────────
    'load-metrics-snapshot': {
        'task': 'backend.services.tasks.task_executor.metrics_snapshot',
        'schedule': 300.0,  # every 5 minutes
    },
    'predictive-scaling-check': {
        'task': 'backend.services.tasks.task_executor.predictive_scale',
        'schedule': 300.0,  # every 5 minutes
    },
    
    # ── Phase 13.4: Continuous Self-Improvement Engine ────────────────────────
    'knowledge-consolidation-weekly': {
        'task': 'backend.services.tasks.task_executor.knowledge_consolidation',
        'schedule': 604800.0,  # weekly
    },
    'performance-optimization-weekly': {
        'task': 'backend.services.tasks.task_executor.performance_optimization',
        'schedule': 604800.0,  # weekly
    },

    # ── Phase 13.6: Intelligent Event Processing ──────────────────────
    'threshold-event-check': {
        'task': 'backend.services.tasks.task_executor.threshold_event_check',
        'schedule': 60.0,   # every 60 seconds
    },
    'external-api-poll': {
        'task': 'backend.services.tasks.task_executor.external_api_poll',
        'schedule': 60.0,   # every 60 seconds
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Federation Tasks
# ──────────────────────────────────────────────────────────────────────────────

def _hmac_sign(signing_key: str, body_bytes: bytes, timestamp: int) -> str:
    """Produce HMAC-SHA256 signature — same logic as FederationService._sign_payload."""
    message = f"{timestamp}:".encode() + body_bytes
    return hmac.new(signing_key.encode(), message, hashlib.sha256).hexdigest()


def _signed_headers(peer_url: str, signing_key: str, body_bytes: bytes) -> dict:
    ts = int(time.time())
    sig = _hmac_sign(signing_key, body_bytes, ts)
    return {
        "Content-Type": "application/json",
        "X-Agentium-Peer-Url": peer_url,
        "X-Agentium-Timestamp": str(ts),
        "X-Agentium-Signature": f"sha256={sig}",
    }


@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
def deliver_federated_task(
    self,
    fed_task_id: str,
    target_url: str,
    peer_url: str,
    signing_key: str,
    payload: dict,
):
    """
    Deliver a delegated task to a peer instance via HMAC-signed HTTP POST.
    Retries with exponential backoff on failure (up to 5 attempts).
    Updates FederatedTask.status to 'delivered' on success or 'failed' after max retries.
    """
    import httpx
    from contextlib import contextmanager
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/agentium")
    engine = create_engine(DATABASE_URL, poolclass=NullPool, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)

    body_bytes = json.dumps(payload, sort_keys=True).encode()
    headers = _signed_headers(peer_url, signing_key, body_bytes)

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(target_url, content=body_bytes, headers=headers)
            resp.raise_for_status()

        # Mark delivered
        db = Session()
        try:
            from backend.models.entities.federation import FederatedTask
            ft = db.query(FederatedTask).filter_by(id=fed_task_id).first()
            if ft:
                ft.status = "delivered"
                db.commit()
        finally:
            db.close()

        logger.info(f"Federation: delivered task {fed_task_id} → {target_url}")
        return {"delivered": True, "fed_task_id": fed_task_id}

    except Exception as exc:
        attempt = self.request.retries + 1
        countdown = (2 ** self.request.retries) * 30  # 30s, 60s, 120s, 240s, 480s
        logger.warning(
            f"Federation: delivery attempt {attempt}/5 failed for {fed_task_id}: {exc}. "
            f"Retrying in {countdown}s."
        )

        if self.request.retries >= self.max_retries:
            # Final failure — mark the record
            db = Session()
            try:
                from backend.models.entities.federation import FederatedTask
                ft = db.query(FederatedTask).filter_by(id=fed_task_id).first()
                if ft:
                    ft.status = "failed"
                    db.commit()
            finally:
                db.close()
            logger.error(f"Federation: giving up on delivery for {fed_task_id} after {attempt} attempts.")
            return {"delivered": False, "fed_task_id": fed_task_id}

        raise self.retry(exc=exc, countdown=countdown)


@celery_app.task
def federation_heartbeat():
    """
    Active heartbeat probe — ping all active peers every 5 minutes.
    Marks unreachable peers as 'suspended'.
    Re-activates previously suspended peers that become reachable again.
    """
    if not os.getenv("FEDERATION_ENABLED", "false").lower() == "true":
        return {"skipped": "federation disabled"}

    import httpx
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/agentium")
    engine = create_engine(DATABASE_URL, poolclass=NullPool, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    db = Session()

    my_base_url = os.getenv("FEDERATION_INSTANCE_URL", "").rstrip("/")
    my_secret = os.getenv("FEDERATION_SHARED_SECRET", "")
    signing_key = hashlib.sha256((my_secret + ":sign").encode()).hexdigest()

    results = {"probed": 0, "alive": 0, "suspended": 0}

    try:
        from backend.models.entities.federation import FederatedInstance
        # Probe active + suspended peers (suspended might have recovered)
        peers = db.query(FederatedInstance).filter(
            FederatedInstance.status.in_(["active", "suspended"])
        ).all()

        for peer in peers:
            results["probed"] += 1
            body = b"{}"
            ts = int(time.time())
            sig = _hmac_sign(signing_key, body, ts)
            try:
                resp = httpx.post(
                    f"{peer.base_url}/api/v1/federation/webhooks/heartbeat",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Agentium-Peer-Url": my_base_url,
                        "X-Agentium-Timestamp": str(ts),
                        "X-Agentium-Signature": f"sha256={sig}",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    peer.last_heartbeat_at = __import__('datetime').datetime.utcnow()
                    if peer.status == "suspended":
                        peer.status = "active"
                        logger.info(f"Federation: peer '{peer.name}' recovered — set active.")
                    results["alive"] += 1
                else:
                    peer.status = "suspended"
                    results["suspended"] += 1
                    logger.warning(f"Federation: peer '{peer.name}' returned {resp.status_code} — suspended.")
            except Exception as e:
                peer.status = "suspended"
                results["suspended"] += 1
                logger.warning(f"Federation: heartbeat to '{peer.name}' failed: {e} — suspended.")

        db.commit()
    finally:
        db.close()

    logger.info(f"Federation heartbeat: {results}")
    return results


@celery_app.task
def federation_cleanup_stale():
    """
    Supplementary stale-peer check — runs hourly as a safety net.
    Suspends peers with no heartbeat beyond FEDERATION_STALE_TIMEOUT_MINUTES.
    """
    if not os.getenv("FEDERATION_ENABLED", "false").lower() == "true":
        return {"skipped": "federation disabled"}

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/agentium")
    engine = create_engine(DATABASE_URL, poolclass=NullPool, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        from backend.services.federation_service import FederationService
        suspended = FederationService.cleanup_stale_peers(db)
        logger.info(f"Federation cleanup: suspended {suspended} stale peer(s).")
        return {"suspended": suspended}
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_federation_result(
    self,
    callback_url: str,
    peer_url: str,
    signing_key: str,
    original_task_id: str,
    local_task_id: str,
    task_status: str,
    result_summary: str,
    result_data: dict = None,
):
    """
    Fire a result callback to the source instance after a federated task completes.
    Called from task_executor.py when a task with federated metadata finishes.
    """
    import httpx

    payload = {
        "original_task_id": original_task_id,
        "local_task_id": local_task_id,
        "status": task_status,
        "result_summary": result_summary,
        "result_data": result_data or {},
    }
    body_bytes = json.dumps(payload, sort_keys=True).encode()
    headers = _signed_headers(peer_url, signing_key, body_bytes)

    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(callback_url, content=body_bytes, headers=headers)
            resp.raise_for_status()
        logger.info(f"Federation: sent result callback to {callback_url} for task {original_task_id}")
        return {"sent": True}
    except Exception as exc:
        countdown = (2 ** self.request.retries) * 60
        logger.warning(f"Federation: result callback failed: {exc}. Retrying in {countdown}s.")
        raise self.retry(exc=exc, countdown=countdown)


# ──────────────────────────────────────────────────────────────────────────────
# Worker startup
# ──────────────────────────────────────────────────────────────────────────────

@worker_ready.connect
def on_worker_ready(**kwargs):
    print("🥬 Celery worker ready for Agentium tasks")
    print("   Task Execution Architecture: Governance Alignment active")
    print("   Federation tasks registered: deliver_federated_task, federation_heartbeat, federation_cleanup_stale, send_federation_result")

    from backend.services.tasks.task_executor import start_imap_receivers
    start_imap_receivers.delay()


if __name__ == '__main__':
    celery_app.start()
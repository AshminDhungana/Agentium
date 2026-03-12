"""
Federation Service 
===============================
Handles peer instance registration, cross-instance messaging, and federated task delegation.

"""

import uuid
import hmac
import hashlib
import time
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.models.entities.federation import FederatedInstance, FederatedTask, FederatedVote
from backend.models.entities.task import Task, TaskStatus, TaskPriority, TaskType
from backend.core.config import settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# HMAC helpers
# ──────────────────────────────────────────────────────────────────────────────

def _sign_payload(secret: str, body_bytes: bytes, timestamp: int) -> str:
    """
    Produce an HMAC-SHA256 signature over (timestamp + body).
    The raw secret is NEVER sent on the wire — only this derived signature is.
    """
    message = f"{timestamp}:".encode() + body_bytes
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _verify_signature(
    stored_hash: str,
    raw_body: bytes,
    incoming_sig: str,
    timestamp: int,
    max_age_seconds: int = 300,
) -> bool:
    """
    1. Check timestamp freshness (prevent replay attacks).
    2. Re-derive expected signature from stored_hash and compare.

    NOTE: stored_hash is SHA-256(secret). We cannot reverse it to get the
    plaintext secret, so we store an additional *signing key* column in the DB.
    See FederatedInstance.signing_key — that is SHA-256(secret + "sign") and is
    used only for HMAC, never for identity verification.

    For backward-compatibility the service also accepts the legacy header-secret
    path (see authenticate_peer_legacy).
    """
    if abs(time.time() - timestamp) > max_age_seconds:
        return False
    expected = _sign_payload(stored_hash, raw_body, timestamp)
    return hmac.compare_digest(expected, incoming_sig)


# ──────────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────────

class FederationService:

    # ── Secret storage ────────────────────────────────────────────────────────

    @staticmethod
    def _hash_secret(secret: str) -> str:
        """Hash a shared secret for identity storage (not for HMAC signing)."""
        return hashlib.sha256(secret.encode()).hexdigest()

    @staticmethod
    def _derive_signing_key(secret: str) -> str:
        """Derive a separate signing key so the identity hash is not reused for HMAC."""
        return hashlib.sha256((secret + ":sign").encode()).hexdigest()

    @staticmethod
    def _verify_secret(secret: str, hashed_secret: str) -> bool:
        return FederationService._hash_secret(secret) == hashed_secret

    # ── Registration ──────────────────────────────────────────────────────────

    @classmethod
    def register_peer(
        cls,
        db: Session,
        name: str,
        base_url: str,
        shared_secret: str,
        trust_level: str = "limited",
        capabilities: Optional[List[str]] = None,
    ) -> FederatedInstance:
        """Register a new peer instance. Stores hashed secret + derived signing key."""
        if not settings.FEDERATION_ENABLED:
            raise HTTPException(status_code=400, detail="Federation is not enabled on this instance.")

        base_url = base_url.rstrip("/")
        existing = db.query(FederatedInstance).filter(FederatedInstance.base_url == base_url).first()
        if existing:
            raise HTTPException(status_code=400, detail="Peer with this base URL already registered.")

        peer = FederatedInstance(
            name=name,
            base_url=base_url,
            shared_secret_hash=cls._hash_secret(shared_secret),
            # signing_key is used for HMAC; stored as a second SHA-256 derivative
            signing_key=cls._derive_signing_key(shared_secret),
            status="active",
            trust_level=trust_level,
            capabilities_shared=capabilities or [],
        )
        db.add(peer)
        db.commit()
        db.refresh(peer)
        logger.info(f"Federation: registered peer '{name}' ({base_url}) trust={trust_level}")
        return peer

    # ── Lookup ────────────────────────────────────────────────────────────────

    @staticmethod
    def get_peer(db: Session, peer_id: str) -> FederatedInstance:
        peer = db.query(FederatedInstance).filter(FederatedInstance.id == peer_id).first()
        if not peer:
            raise HTTPException(status_code=404, detail="Peer not found.")
        return peer

    @staticmethod
    def list_peers(db: Session, skip: int = 0, limit: int = 100) -> List[FederatedInstance]:
        """
        Return registered peer instances.

        Args:
            db:    SQLAlchemy session.
            skip:  Number of records to skip (for pagination). Default 0.
            limit: Maximum number of records to return. Default 100.

        Callers that omit skip/limit get the same behaviour as before
        (all peers up to the default limit), so this change is fully
        backward-compatible.
        """
        return (
            db.query(FederatedInstance)
            .order_by(FederatedInstance.registered_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    # ── Authentication (HMAC) ─────────────────────────────────────────────────

    @staticmethod
    def authenticate_peer_hmac(
        db: Session,
        peer_url: str,
        signature: str,
        timestamp: int,
        raw_body: bytes,
    ) -> FederatedInstance:
        """
        Authenticate an incoming peer request using HMAC-SHA256 signature.
        The peer sends:
          X-Agentium-Peer-Url  : their own base URL (used to look them up)
          X-Agentium-Timestamp : unix timestamp (int)
          X-Agentium-Signature : sha256=<hex>
        """
        if not settings.FEDERATION_ENABLED:
            raise HTTPException(status_code=403, detail="Federation disabled.")

        peer_url = peer_url.rstrip("/")
        peer = db.query(FederatedInstance).filter(FederatedInstance.base_url == peer_url).first()
        if not peer:
            raise HTTPException(status_code=401, detail="Peer not registered.")

        if peer.status != "active":
            raise HTTPException(status_code=403, detail=f"Peer status is '{peer.status}'.")

        # Strip "sha256=" prefix if present
        clean_sig = signature.replace("sha256=", "")
        signing_key = getattr(peer, "signing_key", peer.shared_secret_hash)

        if not _verify_signature(signing_key, raw_body, clean_sig, timestamp):
            raise HTTPException(status_code=401, detail="Invalid or expired signature.")

        peer.last_heartbeat_at = datetime.utcnow()
        db.commit()
        return peer

    @staticmethod
    def authenticate_peer_legacy(
        db: Session,
        base_url: str,
        secret: str,
    ) -> FederatedInstance:
        """
        Legacy header-secret authentication (backward-compatible).
        New deployments should use authenticate_peer_hmac instead.
        """
        if not settings.FEDERATION_ENABLED:
            raise HTTPException(status_code=403, detail="Federation disabled.")

        base_url = base_url.rstrip("/")
        peer = db.query(FederatedInstance).filter(FederatedInstance.base_url == base_url).first()
        if not peer:
            raise HTTPException(status_code=401, detail="Peer not registered.")
        if not FederationService._verify_secret(secret, peer.shared_secret_hash):
            raise HTTPException(status_code=401, detail="Invalid shared secret.")
        if peer.status != "active":
            raise HTTPException(status_code=403, detail=f"Peer status is '{peer.status}'.")

        peer.last_heartbeat_at = datetime.utcnow()
        db.commit()
        return peer

    # ── Outgoing delegation ───────────────────────────────────────────────────

    @classmethod
    def delegate_task(
        cls,
        db: Session,
        target_peer_id: str,
        original_task_id: str,
        payload: Dict[str, Any],
        my_base_url: Optional[str] = None,
        my_secret: Optional[str] = None,
    ) -> FederatedTask:
        """
        Record an outgoing delegated task AND dispatch delivery via Celery.

        Args:
            my_base_url: This instance's public base URL (for the peer to send callbacks to).
            my_secret: The plaintext shared secret for THIS instance → peer direction.
                       Passed through to Celery; never stored.
        """
        peer = cls.get_peer(db, target_peer_id)
        if peer.status != "active":
            raise HTTPException(status_code=400, detail="Target peer is not active.")

        fed_task = FederatedTask(
            target_instance_id=peer.id,
            original_task_id=original_task_id,
            status="pending",
        )
        db.add(fed_task)
        db.commit()
        db.refresh(fed_task)

        # ── Dispatch delivery via Celery (non-blocking) ───────────────────────
        try:
            from backend.services.tasks.task_executor import deliver_federated_task
            deliver_federated_task.delay(
                fed_task_id=fed_task.id,
                target_url=f"{peer.base_url}/api/v1/federation/webhooks/tasks/receive",
                peer_url=(my_base_url or settings.FEDERATION_INSTANCE_URL).rstrip("/"),
                signing_key=cls._derive_signing_key(my_secret) if my_secret else peer.signing_key,
                payload={
                    "original_task_id": original_task_id,
                    "callback_url": f"{(my_base_url or settings.FEDERATION_INSTANCE_URL).rstrip('/')}/api/v1/federation/webhooks/tasks/result",
                    **payload,
                },
            )
            logger.info(f"Federation: queued delivery for federated task {fed_task.id} → {peer.name}")
        except Exception as e:
            # Delivery dispatch failure must not roll back the DB record
            logger.error(f"Federation: failed to dispatch delivery task: {e}")

        return fed_task

    # ── Incoming task ─────────────────────────────────────────────────────────

    @staticmethod
    def receive_delegated_task(
        db: Session,
        source_peer: FederatedInstance,
        original_task_id: str,
        payload: Dict[str, Any],
    ) -> FederatedTask:
        """
        Receive a task delegated from a peer and create a real local Task record
        so Agentium agents on this instance actually pick it up and execute it.
        """
        if source_peer.trust_level == "read_only":
            raise HTTPException(status_code=403, detail="Peer only has read_only access.")

        # ── Create a real Task record ─────────────────────────────────────────
        new_task = Task(
            title=payload.get("title", f"[Federated] Task from {source_peer.name}"),
            description=payload.get("description", f"Task delegated from federated peer '{source_peer.name}'."),
            priority=_safe_enum(TaskPriority, payload.get("priority"), TaskPriority.NORMAL),
            task_type=_safe_enum(TaskType, payload.get("task_type"), TaskType.EXECUTION),
            status=TaskStatus.PENDING,
            created_by="federation",
            requires_deliberation=False,  # Federated tasks skip internal deliberation
            constitutional_basis=f"Delegated by federated peer: {source_peer.name} (trust={source_peer.trust_level})",
            execution_context=str({
                "federated": True,
                "source_instance": source_peer.name,
                "source_instance_id": source_peer.id,
                "source_task_id": original_task_id,
                "callback_url": payload.get("callback_url"),
            }),
        )
        db.add(new_task)
        db.flush()  # Populate new_task.id without committing

        fed_task = FederatedTask(
            source_instance_id=source_peer.id,
            original_task_id=original_task_id,
            local_task_id=new_task.agentium_id,
            status="accepted",
        )
        db.add(fed_task)
        db.commit()
        db.refresh(fed_task)

        logger.info(
            f"Federation: accepted task from '{source_peer.name}' "
            f"→ local task {new_task.agentium_id}"
        )
        return fed_task

    # ── Result callback ───────────────────────────────────────────────────────

    @staticmethod
    def receive_task_result(
        db: Session,
        source_peer: FederatedInstance,
        original_task_id: str,
        local_task_id: str,
        status: str,
        result_summary: str,
        result_data: Optional[Dict[str, Any]] = None,
    ) -> FederatedTask:
        """
        Called when a peer reports completion/failure of a task we delegated.
        Updates our outgoing FederatedTask record and the originating local Task.
        """
        fed_task = (
            db.query(FederatedTask)
            .filter(
                FederatedTask.original_task_id == original_task_id,
                FederatedTask.target_instance_id == source_peer.id,
            )
            .first()
        )
        if not fed_task:
            raise HTTPException(status_code=404, detail="Federated task record not found.")

        fed_task.status = status  # "completed" | "failed"
        fed_task.completed_at = datetime.utcnow() if status == "completed" else None

        # Update the original local task result summary if task still exists
        orig_task = db.query(Task).filter(Task.agentium_id == fed_task.original_task_id).first()
        if orig_task:
            orig_task.result_summary = result_summary
            if status == "completed":
                orig_task.status = TaskStatus.COMPLETED
            elif status == "failed":
                orig_task.status = TaskStatus.FAILED

        db.commit()
        db.refresh(fed_task)
        logger.info(
            f"Federation: received result for original_task={original_task_id} "
            f"status={status} from '{source_peer.name}'"
        )
        return fed_task

    # ── Heartbeat probe ───────────────────────────────────────────────────────

    @classmethod
    def probe_peer(cls, db: Session, peer: FederatedInstance, my_base_url: str, my_signing_key: str) -> bool:
        """
        Send a heartbeat probe to a single peer.
        Returns True if reachable, False otherwise.
        Updates peer.status and peer.last_heartbeat_at accordingly.
        """
        try:
            body = b"{}"
            ts = int(time.time())
            sig = _sign_payload(my_signing_key, body, ts)

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
                peer.last_heartbeat_at = datetime.utcnow()
                if peer.status == "suspended":
                    peer.status = "active"
                db.commit()
                return True
            else:
                logger.warning(f"Federation: heartbeat to '{peer.name}' returned {resp.status_code}")
                peer.status = "suspended"
                db.commit()
                return False
        except Exception as exc:
            logger.warning(f"Federation: heartbeat probe to '{peer.name}' failed: {exc}")
            peer.status = "suspended"
            db.commit()
            return False

    # ── Stale peer cleanup ────────────────────────────────────────────────────

    @staticmethod
    def cleanup_stale_peers(
        db: Session,
        timeout_minutes: Optional[int] = None,
    ) -> int:
        """
        Mark peers as suspended if no heartbeat within timeout window.
        Defaults to settings.FEDERATION_STALE_TIMEOUT_MINUTES (24 h).
        """
        minutes = timeout_minutes or getattr(settings, "FEDERATION_STALE_TIMEOUT_MINUTES", 1440)
        threshold = datetime.utcnow() - timedelta(minutes=minutes)
        stale = (
            db.query(FederatedInstance)
            .filter(
                FederatedInstance.status == "active",
                FederatedInstance.last_heartbeat_at < threshold,
            )
            .all()
        )
        for peer in stale:
            peer.status = "suspended"
            logger.info(f"Federation: suspended stale peer '{peer.name}' (no heartbeat for {minutes} min)")
        if stale:
            db.commit()
        return len(stale)

    # ── Peer management ───────────────────────────────────────────────────────

    @staticmethod
    def delete_peer(db: Session, peer_id: str) -> None:
        peer = db.query(FederatedInstance).filter(FederatedInstance.id == peer_id).first()
        if not peer:
            raise HTTPException(status_code=404, detail="Peer not found.")
        db.delete(peer)
        db.commit()

    @staticmethod
    def update_peer_trust(db: Session, peer_id: str, trust_level: str) -> FederatedInstance:
        allowed = {"full", "limited", "read_only"}
        if trust_level not in allowed:
            raise HTTPException(status_code=400, detail=f"trust_level must be one of {allowed}")
        peer = FederationService.get_peer(db, peer_id)
        peer.trust_level = trust_level
        db.commit()
        db.refresh(peer)
        return peer

    # ── Federated task listing ────────────────────────────────────────────────

    @staticmethod
    def list_federated_tasks(db: Session, limit: int = 50) -> List[FederatedTask]:
        return (
            db.query(FederatedTask)
            .order_by(FederatedTask.delegated_at.desc())
            .limit(limit)
            .all()
        )


# ──────────────────────────────────────────────────────────────────────────────
# Utility
# ──────────────────────────────────────────────────────────────────────────────

def _safe_enum(enum_cls, value: Optional[str], default):
    """Return enum member for value, or default if value is invalid/None."""
    if value is None:
        return default
    try:
        return enum_cls(value)
    except ValueError:
        return default
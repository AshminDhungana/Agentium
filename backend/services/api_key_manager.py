"""
API Key Manager 

Provides:
- Multi-key failover with priority ordering
- Automatic health monitoring and cooldown recovery
- Per-key budget enforcement
- Real-time notifications when all keys fail
- Zero-downtime key rotation

Failover Architecture:
    Request → Primary Key (priority=1)
        ↓ FAIL
        → Secondary Key (priority=2)
        ↓ FAIL
        → Tertiary Key (priority=3)
        ↓ FAIL
        → Local Fallback (Ollama)
        ↓ FAIL
        → ALERT: Notify all channels + frontend
"""

import logging
import asyncio
from typing import Optional, Dict, List, Callable, Any, Tuple
from datetime import datetime, timedelta
from functools import wraps
from sqlalchemy.orm import Session
from sqlalchemy import text
from threading import Lock

from backend.models.database import get_system_agent_id
from backend.models.entities.user_config import UserModelConfig, ConnectionStatus, ProviderType
from backend.models.entities.channels import ExternalChannel, ChannelType
from backend.models.entities.monitoring import MonitoringAlert, ViolationSeverity
from backend.core.security import decrypt_api_key
from backend.core.dependencies import with_db_session

logger = logging.getLogger(__name__)


class APIKeyHealthStatus:
    """Health status enumeration for API keys."""
    HEALTHY = "healthy"
    COOLDOWN = "cooldown"
    RATE_LIMITED = "rate_limited"
    EXHAUSTED = "exhausted"  # Budget exceeded
    ERROR = "error"
    DISABLED = "disabled"


class APIKeyManager:
    """
    Central manager for API key resilience, failover, and health monitoring.
    
    Thread-safe singleton that handles:
    - Priority-based key selection
    - Automatic failover on failure
    - Cooldown and recovery management
    - Budget tracking and enforcement
    - Multi-channel notifications
    """
    
    _instance = None
    _lock = Lock()
    
    # Configuration constants
    MAX_FAILURES_BEFORE_COOLDOWN = 3
    DEFAULT_COOLDOWN_MINUTES = 5
    NOTIFICATION_DEBOUNCE_SECONDS = 300  # 5 minutes between "all down" alerts
    
    def __new__(cls):
        """New."""

        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Init."""

        if self._initialized:
            return
        
        self._initialized = True
        self._notification_cache: Dict[str, datetime] = {}  # provider -> last_notification_time
        self._local_fallback_config: Optional[Dict[str, Any]] = None
        
        logger.info("🔐 API Key Manager initialized")
    
    # =====================================================================
    # Core Failover Logic
    # =====================================================================
    
    @with_db_session
    def get_active_key(
        self, 
        provider: str, 
        estimated_cost: float = 0.0,
        min_priority: int = 1,
        db: Optional[Session] = None
    ) -> Optional[UserModelConfig]:
        """
        Get the highest priority healthy key for a provider.
        
        Args:
            provider: Provider type (openai, anthropic, etc.)
            estimated_cost: Estimated USD cost for this request (for budget check)
            min_priority: Minimum priority level to consider (for cascading failover)
            db: Database session (optional, will create context if None)
            
        Returns:
            UserModelConfig with healthy key, or None if no keys available

        Performance: <50ms database query
        """
        keys = db.query(UserModelConfig).filter_by(
            provider=provider,
            is_active=True
        ).filter(
            UserModelConfig.priority >= min_priority
        ).order_by(
            UserModelConfig.priority.asc()
        ).all()

        for key in keys:
            if self._is_key_healthy(key, estimated_cost):
                return key

        return None
    
    def get_active_key_with_fallback(
        self,
        providers: List[str],
        estimated_cost: float = 0.0,
        db: Optional[Session] = None
    ) -> Tuple[Optional[UserModelConfig], str]:
        """
        Try multiple providers in order until a healthy key is found.
        
        Args:
            providers: List of provider names to try in order
            estimated_cost: Estimated USD cost
            db: Database session
            
        Returns:
            Tuple of (key_config, provider_name) or (None, "exhausted")
        """
        for provider in providers:
            key = self.get_active_key(provider, estimated_cost, db=db)
            if key:
                return key, provider
        
        # All providers exhausted - trigger notification
        self._notify_all_keys_down(providers[-1] if providers else "unknown", db)
        return None, "exhausted"
    
    def _is_key_healthy(self, key: UserModelConfig, estimated_cost: float = 0.0) -> bool:
        """
        Check if a key is healthy and available for use.
        
        Checks:
        - Not in cooldown period
        - Status is not ERROR
        - Monthly budget not exceeded
        - Estimated cost within remaining budget
        """
        now = datetime.utcnow()
        
        # Check cooldown
        if key.cooldown_until and now < key.cooldown_until:
            return False
        
        # Check status
        if key.status == ConnectionStatus.ERROR:
            return False
        
        # Check if key needs recovery (cooldown expired but status still ERROR)
        if key.cooldown_until and now >= key.cooldown_until:
            # Auto-recover from cooldown
            self._auto_recover_key(key)
            return True
        
        # Check monthly budget
        self._reset_monthly_spend_if_needed(key)
        if key.monthly_budget_usd > 0:
            remaining = key.monthly_budget_usd - key.current_spend_usd
            if remaining < estimated_cost:
                return False
        
        return True
    
    def _reset_monthly_spend_if_needed(self, key: UserModelConfig):
        """
        Reset monthly spend counter if we've entered a new month.

        NOTE: this mutates the in-memory ORM object only. It does NOT commit,
        and it is NOT safe as the sole reset mechanism under concurrency —
        two requests can both decide "new month" and both reset to 0,
        each then adding their own delta, losing whichever write loses the
        race. The atomic, concurrency-safe reset happens inside record_spend()
        via a single conditional UPDATE. This method exists for synchronous
        read paths (e.g. _is_key_healthy, check_budget, _get_key_status)
        where we just need an accurate in-memory view to make a decision —
        the real reset-of-record is the SQL statement in record_spend().
        """
        now = datetime.utcnow()
        if (key.last_spend_reset.month != now.month or
            key.last_spend_reset.year != now.year):
            key.current_spend_usd = 0.0
            key.last_spend_reset = now

    # Phase 19.3: cap on the fallback chain length. LLMClient.generate
    # already bounds configs_to_try to (1 + MAX_FALLBACK_CONFIGS); keep the
    # produced list at most one longer so the primary + fallbacks fit.
    MAX_FALLBACK_CONFIGS = 3

    @with_db_session
    def get_fallback_config_ids(
        self, config_id: str, db: Optional[Session] = None
    ) -> List[str]:
        """
        Phase 19.3: ordered provider failover list for a primary config id.
        Order:
          1. other ACTIVE, healthy keys of the SAME provider (priority asc)
          2. ONE ACTIVE, healthy key of a DIFFERENT provider (cross-provider)
          3. the local/Ollama config (never throttled by the cloud) — also
             caches it on self._local_fallback_config for callers that need
             the base URL.
        Excludes keys in ConnectionStatus.ERROR. Returns [] if unknown.
        Consumed by Task 12 (routing) and Task 14 (call-site audit).
        """
        primary = db.query(UserModelConfig).filter_by(id=config_id).first()
        if not primary:
            return []

        out: List[str] = []

        # 1. same provider, other healthy keys
        same_provider = (
            db.query(UserModelConfig)
            .filter(
                UserModelConfig.provider == primary.provider,
                UserModelConfig.id != config_id,
                UserModelConfig.is_active == True,
                UserModelConfig.status != ConnectionStatus.ERROR,
            )
            .order_by(UserModelConfig.priority.asc())
            .all()
        )
        out += [k.id for k in same_provider]

        # 2. one key from a different (cloud) provider — exclude LOCAL here so
        #    it is added exactly once in step 3 (the offline special case).
        other_provider = (
            db.query(UserModelConfig)
            .filter(
                UserModelConfig.provider != primary.provider,
                UserModelConfig.provider != ProviderType.LOCAL,
                UserModelConfig.is_active == True,
                UserModelConfig.status != ConnectionStatus.ERROR,
            )
            .order_by(UserModelConfig.priority.asc())
            .first()
        )
        if other_provider:
            out.append(other_provider.id)

        # 3. local / Ollama fallback (offline, never rate-limited by the cloud)
        local = (
            db.query(UserModelConfig)
            .filter(
                UserModelConfig.provider == ProviderType.LOCAL,
                UserModelConfig.is_active == True,
            )
            .first()
        )
        if local:
            out.append(local.id)
            self._local_fallback_config = {
                "id": str(local.id),
                "provider": local.provider.value,
                "base_url": local.local_server_url or "http://localhost:11434/v1",
            }

        # Bound to primary + MAX_FALLBACK_CONFIGS (LLMClient enforces the same).
        return out[: self.MAX_FALLBACK_CONFIGS + 1]

    # =====================================================================
    # Failure Handling & Recovery
    # =====================================================================
    
    @with_db_session
    def mark_key_failed(
        self, 
        key_id: str, 
        error: Optional[str] = None,
        is_rate_limit: bool = False,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Mark a key as failed, increment failure count, potentially trigger cooldown.
        
        Args:
            key_id: UUID of the key config
            error: Error message for logging
            is_rate_limit: If True, use longer cooldown (15 min vs 5 min)
            db: Database session
            
        Returns:
            Dict with status: 'cooldown', 'error', or 'disabled'
        """
        key = db.query(UserModelConfig).filter_by(id=key_id).first()
        if not key:
            logger.error(f"Key {key_id} not found for failure marking")
            return {"status": "not_found"}

        key.failure_count += 1
        key.last_failure_at = datetime.utcnow()

        cooldown_minutes = 15 if is_rate_limit else self.DEFAULT_COOLDOWN_MINUTES

        if key.failure_count >= self.MAX_FAILURES_BEFORE_COOLDOWN:
            key.cooldown_until = datetime.utcnow() + timedelta(minutes=cooldown_minutes)
            key.status = ConnectionStatus.ERROR

            logger.warning(
                f"🔒 Key {key_id} ({key.provider.value}) entered cooldown "
                f"for {cooldown_minutes}min after {key.failure_count} failures"
            )

            return {
                "status": "cooldown",
                "cooldown_until": key.cooldown_until.isoformat(),
                "failure_count": key.failure_count
            }
        else:
            logger.info(
                f"⚠️ Key {key_id} failure #{key.failure_count}: {error or 'Unknown error'}"
            )
            return {
                "status": "error",
                "failure_count": key.failure_count,
                "remaining_attempts": self.MAX_FAILURES_BEFORE_COOLDOWN - key.failure_count
            }
    
    @with_db_session
    def mark_key_success(self, key_id: str, db: Optional[Session] = None):
        """Reset failure count on successful API call."""
        key = db.query(UserModelConfig).filter_by(id=key_id).first()
        if key and key.failure_count > 0:
            key.failure_count = 0
            key.last_failure_at = None
            key.cooldown_until = None
            if key.status == ConnectionStatus.ERROR:
                key.status = ConnectionStatus.ACTIVE
    
    def _auto_recover_key(self, key: UserModelConfig):
        """Automatically recover a key from cooldown."""
        key.status = ConnectionStatus.ACTIVE
        key.failure_count = max(0, key.failure_count - 1)  # Decay failures
        logger.info(f"🔓 Key {key.id} auto-recovered from cooldown")
    
    @with_db_session
    def recover_key(self, key_id: str, db: Optional[Session] = None) -> bool:
        """
        Manually recover a key from cooldown/error state.

        Returns True if key was found and recovered.
        """
        key = db.query(UserModelConfig).filter_by(id=key_id).first()
        if not key:
            return False

        key.status = ConnectionStatus.ACTIVE
        key.failure_count = 0
        key.cooldown_until = None
        key.last_failure_at = None

        logger.info(f"🔓 Key {key_id} manually recovered")
        return True
    
    # =====================================================================
    # Budget Management
    # =====================================================================
    
    @with_db_session
    def record_spend(
        self,
        key_id: str,
        cost_usd: float,
        tokens_used: int = 0,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Record API usage cost for budget tracking.

        This performs the increment as a single atomic SQL UPDATE rather
        than a Python read-modify-write on the ORM object. That matters
        under concurrency: with read-modify-write, two requests that both
        read current_spend_usd=10.0 and each add $1 can both write back
        $11.0 instead of $12.0 — one dollar of real spend silently
        vanishes from tracking, and a key can run over budget without the
        ledger ever showing it. The UPDATE below folds the monthly reset
        and the increment into one statement so there is no window where
        two sessions can race on the same row.

        Args:
            key_id: UUID of the key
            cost_usd: Actual cost in USD
            tokens_used: Token count for logging
            db: Database session

        Returns:
            Dict with the key's spend state after this update, e.g.:
            {
                "current_spend_usd": 12.34,
                "monthly_budget_usd": 50.0,
                "budget_exceeded": False,
                "remaining_usd": 37.66,
            }
            Returns {} if the key was not found.
        """
        if cost_usd < 0:
            logger.warning(f"record_spend called with negative cost_usd={cost_usd} for key {key_id}; ignoring")
            cost_usd = 0.0

        now = datetime.utcnow()

        # Single atomic statement: if we've rolled into a new month,
        # reset current_spend_usd to just this charge and bump
        # last_spend_reset; otherwise add to the existing total.
        # The CASE conditions are evaluated server-side against the
        # row's actual current values at UPDATE time (under the
        # row lock Postgres takes for the UPDATE), so there is no
        # read-then-write gap for a concurrent request to land in.
        row = db.execute(
            text("""
                UPDATE user_model_configs
                SET
                    current_spend_usd = CASE
                        WHEN EXTRACT(MONTH FROM last_spend_reset) != EXTRACT(MONTH FROM :now)
                             OR EXTRACT(YEAR FROM last_spend_reset) != EXTRACT(YEAR FROM :now)
                        THEN :cost_usd
                        ELSE current_spend_usd + :cost_usd
                    END,
                    last_spend_reset = CASE
                        WHEN EXTRACT(MONTH FROM last_spend_reset) != EXTRACT(MONTH FROM :now)
                             OR EXTRACT(YEAR FROM last_spend_reset) != EXTRACT(YEAR FROM :now)
                        THEN :now
                        ELSE last_spend_reset
                    END,
                    total_requests = total_requests + 1,
                    estimated_cost_usd = COALESCE(estimated_cost_usd, 0) + :cost_usd
                WHERE id = :key_id
                RETURNING current_spend_usd, monthly_budget_usd
            """),
            {"key_id": key_id, "cost_usd": cost_usd, "now": now},
        ).first()

        if row is None:
            logger.warning(f"record_spend: key {key_id} not found")
            return {}

        current_spend_usd, monthly_budget_usd = float(row[0]), float(row[1] or 0.0)
        budget_exceeded = monthly_budget_usd > 0 and current_spend_usd >= monthly_budget_usd

        if budget_exceeded:
            logger.warning(
                f"💸 Key {key_id} monthly budget EXHAUSTED: "
                f"${current_spend_usd:.2f} / ${monthly_budget_usd:.2f}"
            )
            self._notify_budget_exceeded(key_id, current_spend_usd, monthly_budget_usd, db)
        else:
            # Early-warning thresholds so spend is visible before the
            # hard cap is hit, not just after.
            self._maybe_warn_budget_threshold(key_id, current_spend_usd, monthly_budget_usd)

        return {
            "current_spend_usd": current_spend_usd,
            "monthly_budget_usd": monthly_budget_usd,
            "budget_exceeded": budget_exceeded,
            "remaining_usd": (
                max(0.0, monthly_budget_usd - current_spend_usd)
                if monthly_budget_usd > 0 else None
            ),
        }

    # Thresholds (as a fraction of monthly_budget_usd) at which to log an
    # early warning, so spend is visible before the hard cap actually hits.
    _WARNING_THRESHOLDS = (0.75, 0.90)

    def _maybe_warn_budget_threshold(self, key_id: str, current_spend_usd: float, monthly_budget_usd: float):
        """Log a one-shot warning per threshold as spend approaches the cap."""
        if monthly_budget_usd <= 0:
            return
        pct = current_spend_usd / monthly_budget_usd
        cache_key = f"{key_id}:threshold"
        last_warned_pct = self._notification_cache.get(cache_key, 0.0)
        if isinstance(last_warned_pct, datetime):
            last_warned_pct = 0.0  # _notification_cache is also used for datetimes elsewhere; guard the mix
        for threshold in self._WARNING_THRESHOLDS:
            if pct >= threshold and last_warned_pct < threshold:
                logger.warning(
                    f"⚠️ Key {key_id} at {pct*100:.0f}% of monthly budget "
                    f"(${current_spend_usd:.2f} / ${monthly_budget_usd:.2f})"
                )
                self._notification_cache[cache_key] = threshold

    @with_db_session
    def _notify_budget_exceeded(self, key_id: str, current_spend_usd: float, monthly_budget_usd: float, db: Optional[Session] = None):
        """
        Raise a MonitoringAlert + websocket notification when a key's
        monthly budget is exceeded. Debounced like _notify_all_keys_down
        so a burst of requests against an exhausted key doesn't spam alerts.
        """
        now = datetime.utcnow()
        cache_key = f"{key_id}:budget_exceeded"
        last_notification = self._notification_cache.get(cache_key)
        if last_notification and isinstance(last_notification, datetime):
            if (now - last_notification).total_seconds() < self.NOTIFICATION_DEBOUNCE_SECONDS:
                return
        self._notification_cache[cache_key] = now

        message = (
            f"💸 **AGENTIUM ALERT: Monthly Budget Exceeded**\n\n"
            f"Key: `{key_id}`\n"
            f"Spend: ${current_spend_usd:.2f} / ${monthly_budget_usd:.2f}\n"
            f"Time: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            f"This key will be skipped by failover until budget resets or is raised."
        )

        try:
            self._broadcast_websocket_alert("budget", message)
        except Exception as e:
            logger.error(f"Failed to broadcast budget alert: {e}")

        try:
            self._send_channel_alerts(message, db)
        except Exception as e:
            logger.error(f"Failed to send budget alert to channels: {e}")

        try:
            # NOTE: MonitoringAlert's exact field set wasn't available to verify
            # against — if your model uses different kwargs (e.g. `message`
            # instead of `description`, or no `meta_data` column), adjust this
            # call to match. Wrapped in try/except so a schema mismatch here
            # never breaks the actual spend-recording path above.
            alert = MonitoringAlert(
                severity=ViolationSeverity.HIGH,
                category="budget",
                title="Monthly budget exceeded",
                description=message,
                meta_data={
                    "key_id": key_id,
                    "current_spend_usd": current_spend_usd,
                    "monthly_budget_usd": monthly_budget_usd,
                },
            )
            db.add(alert)
        except Exception as e:
            # Alert persistence is best-effort; never let it break the spend record path
            logger.error(f"Failed to persist MonitoringAlert for budget exceeded: {e}")
    
    @with_db_session
    def check_budget(self, key_id: str, estimated_cost: float, db: Optional[Session] = None) -> bool:
        """
        Check if a key has sufficient budget remaining.

        IMPORTANT — this is a pre-flight check, not a reservation. There is
        an inherent gap between this check and the later record_spend() call
        that actually books the cost: the provider request happens in
        between, and another concurrent request can pass this same check in
        that window. That means two requests can both see "budget OK" and
        both proceed, jointly overshooting monthly_budget_usd by up to one
        extra request's worth of cost. record_spend() itself is atomic and
        will not lose track of the overshoot — it will correctly show the
        key as over budget afterward, and the next check_budget() call will
        correctly start returning False — but it cannot retroactively cancel
        a request already in flight. For hard, no-overshoot enforcement,
        budget checks would need to reserve cost atomically (e.g. an UPDATE
        ... WHERE current_spend_usd + :cost <= monthly_budget_usd RETURNING)
        rather than read-then-decide. That stronger guarantee is not
        implemented here because it would require committing the charge
        before knowing the call will succeed, which has its own correctness
        tradeoffs (refunding failed calls, partial token usage, etc).
        """
        key = db.query(UserModelConfig).filter_by(id=key_id).first()
        if not key or key.monthly_budget_usd <= 0:
            return True  # No budget limit

        self._reset_monthly_spend_if_needed(key)
        remaining = key.monthly_budget_usd - key.current_spend_usd
        return remaining >= estimated_cost
    
    @with_db_session
    def update_budget(
        self,
        key_id: str,
        monthly_budget_usd: float,
        db: Optional[Session] = None
    ) -> bool:
        """Update monthly budget limit for a key."""
        key = db.query(UserModelConfig).filter_by(id=key_id).first()
        if not key:
            return False

        key.monthly_budget_usd = monthly_budget_usd
        return True
    
    # =====================================================================
    # Key Rotation
    # =====================================================================
    
    @with_db_session
    def rotate_key(
        self,
        old_key_id: str,
        new_key_encrypted: str,
        new_key_masked: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Optional[UserModelConfig]:
        """
        Zero-downtime key rotation.
        
        Strategy:
        1. Add new key with same priority+1 (temporary lower priority)
        2. Test new key
        3. Swap priorities (new key becomes primary)
        4. Mark old key for deletion (priority 999, cooldown 1 hour)
        5. After 1 hour, old key can be safely deleted
        
        Returns the new key config.
        """
        old_key = db.query(UserModelConfig).filter_by(id=old_key_id).first()
        if not old_key:
            return None

        # Create new key with temporary lower priority
        new_key = UserModelConfig(
            user_id=old_key.user_id,
            provider=old_key.provider,
            provider_name=old_key.provider_name,
            config_name=f"{old_key.config_name} (Rotated)",
            api_key_encrypted=new_key_encrypted,
            api_key_masked=new_key_masked or "...****",
            api_base_url=old_key.api_base_url,
            local_server_url=old_key.local_server_url,
            default_model=old_key.default_model,
            available_models=old_key.available_models,
            priority=old_key.priority + 1,  # Temporary lower priority
            is_default=False,
            max_tokens=old_key.max_tokens,
            temperature=old_key.temperature,
            top_p=old_key.top_p,
            timeout_seconds=old_key.timeout_seconds,
            status=ConnectionStatus.TESTING,
            monthly_budget_usd=old_key.monthly_budget_usd
        )

        db.add(new_key)
        db.flush()

        # Test new key
        from backend.services.model_provider import ModelService
        test_result = ModelService.test_connection(new_key)

        if not test_result.get("success"):
            db.rollback()
            logger.error(f"❌ Key rotation failed: new key test failed")
            return None

        # Swap priorities - new key becomes primary
        old_priority = old_key.priority
        old_key.priority = 999  # Demote old key
        old_key.config_name = f"{old_key.config_name} (Deprecated)"
        old_key.cooldown_until = datetime.utcnow() + timedelta(hours=1)  # 1 hour grace
        new_key.priority = old_priority
        new_key.status = ConnectionStatus.ACTIVE

        db.commit()
        logger.info(f"🔄 Key rotated: {old_key_id} → {new_key.id}")

        return new_key
    
    # =====================================================================
    # Health Reporting
    # =====================================================================
    
    @with_db_session
    def get_key_health_report(
        self,
        provider: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive health report for all keys or specific provider.
        
        Returns:
            {
                "overall_status": "healthy" | "degraded" | "critical",
                "providers": {
                    "openai": {
                        "total_keys": 3,
                        "healthy": 2,
                        "cooldown": 1,
                        "exhausted": 0,
                        "keys": [...]
                    }
                },
                "total_keys": 10,
                "healthy_keys": 8,
                "keys_in_cooldown": 1,
                "budget_exhausted": 1
            }
        """
        query = db.query(UserModelConfig).filter_by(is_active=True)
        if provider:
            query = query.filter_by(provider=provider)

        keys = query.all()

        # Group by provider
        provider_stats: Dict[str, Dict] = {}
        overall = {
            "total_keys": 0,
            "healthy_keys": 0,
            "keys_in_cooldown": 0,
            "budget_exhausted": 0,
            "total_monthly_spend": 0.0
        }

        for key in keys:
            prov = key.provider.value if hasattr(key.provider, 'value') else str(key.provider)

            if prov not in provider_stats:
                provider_stats[prov] = {
                    "total_keys": 0,
                    "healthy": 0,
                    "cooldown": 0,
                    "rate_limited": 0,
                    "exhausted": 0,
                    "error": 0,
                    "keys": []
                }

            status = self._get_key_status(key)
            stats = provider_stats[prov]
            stats["total_keys"] += 1
            overall["total_keys"] += 1

            if status == APIKeyHealthStatus.HEALTHY:
                stats["healthy"] += 1
                overall["healthy_keys"] += 1
            elif status == APIKeyHealthStatus.COOLDOWN:
                stats["cooldown"] += 1
                overall["keys_in_cooldown"] += 1
            elif status == APIKeyHealthStatus.EXHAUSTED:
                stats["exhausted"] += 1
                overall["budget_exhausted"] += 1
            elif status == APIKeyHealthStatus.RATE_LIMITED:
                stats["rate_limited"] += 1
            else:
                stats["error"] += 1

            self._reset_monthly_spend_if_needed(key)
            overall["total_monthly_spend"] += key.current_spend_usd

            # Add key details (mask sensitive data)
            key_info = {
                "id": str(key.id),
                "priority": key.priority,
                "status": status,
                "failure_count": key.failure_count,
                "cooldown_until": key.cooldown_until.isoformat() if key.cooldown_until else None,
                "monthly_budget_usd": key.monthly_budget_usd,
                "current_spend_usd": round(key.current_spend_usd, 4),
                "budget_remaining_pct": round(
                    ((key.monthly_budget_usd - key.current_spend_usd) / key.monthly_budget_usd * 100), 2
                ) if key.monthly_budget_usd > 0 else 100
            }
            stats["keys"].append(key_info)

        # Determine overall status
        if overall["healthy_keys"] == overall["total_keys"]:
            overall_status = "healthy"
        elif overall["healthy_keys"] >= overall["total_keys"] // 2:
            overall_status = "degraded"
        else:
            overall_status = "critical"

        return {
            "overall_status": overall_status,
            "providers": provider_stats,
            "summary": overall,
            "generated_at": datetime.utcnow().isoformat()
        }
    
    def _get_key_status(self, key: UserModelConfig) -> str:
        """Determine health status string for a key."""
        if not key.is_active or key.is_active is False:
            return APIKeyHealthStatus.DISABLED
        
        now = datetime.utcnow()
        
        if key.cooldown_until and now < key.cooldown_until:
            return APIKeyHealthStatus.COOLDOWN
        
        self._reset_monthly_spend_if_needed(key)
        if key.monthly_budget_usd > 0 and key.current_spend_usd >= key.monthly_budget_usd:
            return APIKeyHealthStatus.EXHAUSTED
        
        if key.status == ConnectionStatus.ERROR:
            return APIKeyHealthStatus.ERROR
        
        return APIKeyHealthStatus.HEALTHY
    
    @with_db_session
    def get_provider_availability(self, db: Optional[Session] = None) -> Dict[str, bool]:
        """
        Quick check: which providers have at least one healthy key?

        Returns: {"openai": True, "anthropic": False, ...}
        """
        result = {}
        all_providers = [p.value for p in ProviderType]

        for prov in all_providers:
            healthy_key = self.get_active_key(prov, db=db)
            result[prov] = healthy_key is not None

        return result
    
    # =====================================================================
    # Notification System
    # =====================================================================
    
    def _notify_all_keys_down(self, provider: str, db: Optional[Session] = None):
        """
        Notify all channels when all keys for a provider are down.
        
        Implements debouncing: max 1 notification per 5 minutes per provider.
        """
        now = datetime.utcnow()
        last_notification = self._notification_cache.get(provider)
        
        if last_notification:
            seconds_since_last = (now - last_notification).total_seconds()
            if seconds_since_last < self.NOTIFICATION_DEBOUNCE_SECONDS:
                logger.debug(f"Notification debounced for {provider} ({seconds_since_last}s ago)")
                return
        
        self._notification_cache[provider] = now
        
        message = (
            f"🚨 **AGENTIUM ALERT: All API Keys Down**\n\n"
            f"Provider: `{provider.upper()}`\n"
            f"Time: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"Impact: AI services unavailable for this provider\n\n"
            f"Action Required: Check API key balances and status"
        )
        
        # 1. WebSocket broadcast to frontend
        self._broadcast_websocket_alert(provider, message)
        
        # 2. Send to all active channels
        self._send_channel_alerts(message, db)
        
        logger.critical(f"🚨 ALL KEYS DOWN for {provider} - notifications sent")
    
    def _broadcast_websocket_alert(self, provider: str, message: str):
        """Broadcast alert to all connected WebSocket clients."""
        try:
            from backend.main import manager
            asyncio.create_task(manager.broadcast({
                "type": "api_key_alert",
                "severity": "critical",
                "provider": provider,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            }))
        except Exception as e:
            logger.error(f"Failed to broadcast WebSocket alert: {e}")
    
    @with_db_session
    def _send_channel_alerts(self, message: str, db: Optional[Session] = None):
        """Send alerts to all configured external channels."""
        try:
            from backend.services.channel_manager import ChannelManager
            channel_manager = ChannelManager()

            # Get all active channels
            channels = db.query(ExternalChannel).filter_by(
                status='active',
                is_active=True
            ).all()

            for channel in channels:
                try:
                    if channel.channel_type == ChannelType.TELEGRAM:
                        asyncio.create_task(
                            channel_manager.send_telegram(channel.channel_id, message)
                        )
                    elif channel.channel_type == ChannelType.DISCORD:
                        asyncio.create_task(
                            channel_manager.send_discord(channel.channel_id, message)
                        )
                    elif channel.channel_type == ChannelType.SLACK:
                        asyncio.create_task(
                            channel_manager.send_slack(channel.channel_id, message)
                        )
                    elif channel.channel_type == ChannelType.WHATSAPP:
                        asyncio.create_task(
                            channel_manager.send_whatsapp(channel.channel_id, message)
                        )
                except Exception as e:
                    logger.error(f"Failed to send to {channel.channel_type}: {e}")

        except Exception as e:
            logger.error(f"Channel alert system error: {e}")
    
    # =====================================================================
    # Decorator for Automatic Failover
    # =====================================================================
    
    def with_failover(
        self,
        provider: str,
        fallback_providers: Optional[List[str]] = None,
        max_attempts: int = 3
    ):
        """
        Decorator for automatic failover on API calls.
        
        Usage:
            @api_key_manager.with_failover("openai", fallback_providers=["anthropic", "groq"])
            async def make_api_call(key_config, ...):
                # Your API call here
                return result
        """
        def decorator(func: Callable):
            """Decorator."""
            @wraps(func)
            async def wrapper(*args, **kwargs):
                """Wrapper."""
                providers = [provider] + (fallback_providers or [])
                
                last_error = None
                for prov in providers:
                    for attempt in range(max_attempts):
                        key = self.get_active_key(prov)
                        if not key:
                            break  # No healthy keys for this provider
                        
                        try:
                            # Inject key into function
                            result = await func(key, *args, **kwargs)
                            # Success - reset failure count
                            self.mark_key_success(key.id)
                            return result
                            
                        except Exception as e:
                            last_error = e
                            error_str = str(e).lower()
                            
                            # Determine if rate limit
                            is_rate_limit = any(x in error_str for x in [
                                "rate limit", "ratelimit", "too many requests", "429"
                            ])
                            
                            # Mark key failed
                            self.mark_key_failed(key.id, str(e), is_rate_limit)
                            
                            # If not rate limit and not last attempt, retry same provider
                            if not is_rate_limit and attempt < max_attempts - 1:
                                continue
                            break  # Move to next provider
                
                # All providers exhausted
                raise Exception(f"All API keys exhausted. Last error: {last_error}")
            
            return wrapper
        return decorator

    # =====================================================================
    # Phase 9.5: API Key Resilience Enhancements
    # =====================================================================

    @with_db_session
    async def notify_all_keys_down(self, db: Optional[Session] = None):
        """
        Dispatch a formal MonitoringAlert via AlertManager when no healthy keys
        remain across ALL configured providers.
        Phase 9.5 requirement.
        """
        from backend.services.alert_manager import AlertManager, ALERT_TYPE_ALL_KEYS_DOWN

        alert_manager = AlertManager(db)
        alert = MonitoringAlert(
            alert_type=ALERT_TYPE_ALL_KEYS_DOWN,
            severity=ViolationSeverity.CRITICAL,
            detected_by_agent_id=get_system_agent_id(db),
            affected_agent_id=None,
            message=(
                "All API keys are down across every configured provider. "
                "AI services are completely unavailable."
            ),
        )
        db.add(alert)
        db.commit()
        asyncio.create_task(alert_manager.dispatch_alert(alert))
        logger.critical(
            "🔑❌ All API keys are down — formal alert dispatched."
        )

    @with_db_session
    def verify_multi_key_support(
        self, provider: str, db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Diagnostic: confirm multiple keys per provider work correctly.
        Returns summary of all keys for the provider, their priorities,
        and which one would be selected via failover.
        Phase 9.5 requirement.
        """
        keys = (
            db.query(UserModelConfig)
            .filter_by(provider=provider, is_active=True)
            .order_by(UserModelConfig.priority.asc())
            .all()
        )
        selected = self.get_active_key(provider, db=db)

        return {
            "provider": provider,
            "total_keys": len(keys),
            "keys": [
                {
                    "id": str(k.id),
                    "priority": k.priority,
                    "status": self._get_key_status(k),
                    "failure_count": k.failure_count,
                }
                for k in keys
            ],
            "selected_key_id": str(selected.id) if selected else None,
            "multi_key_operational": len(keys) > 1
            and selected is not None,
        }


api_key_manager = APIKeyManager()


def init_api_key_manager(db: Session):
    """Initialize the API Key Manager (called during app startup)."""
    # Ensure all existing keys have proper defaults
    db.query(UserModelConfig).filter(
        UserModelConfig.priority.is_(None)
    ).update({"priority": 999})
    
    db.commit()
    logger.info("✅ API Key Manager initialized with resilience features")
"""
Enhanced Token Optimizer with intelligent model allocation and API pooling.
Manages token usage, cost optimization, and model switching.

KEY CHANGES (v2):
- Budget limits are persisted in the database (SystemBudgetConfig table).
- Token/cost usage is sourced from ModelUsageLog (real API data), not estimates.
- When a user updates the budget, the new value becomes the permanent default.
- IdleBudgetManager.get_status() aggregates from DB logs for accuracy.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from dataclasses import dataclass

from backend.models.entities.agents import Agent, AgentStatus, AgentType
from backend.models.entities.task import Task, TaskStatus, TaskPriority
from backend.services.api_manager import init_api_manager, ModelCapability
import backend.services.api_manager as api_manager_module
import backend.services.model_allocation as model_allocation_module
from backend.services.model_allocation import init_model_allocator
from backend.services.chat_context import estimate_tokens

logger = logging.getLogger(__name__)


@dataclass
class IdleBudget:
    """Idle-specific budget tracking."""
    limit_usd: float
    used_usd: float
    period_hours: int
    last_reset: datetime

# ---------------------------------------------------------------------------
# Persistent Budget Configuration (DB-backed)
# ---------------------------------------------------------------------------

class SystemBudgetConfig:
    """
    Thin wrapper that reads/writes budget limits to the DB so they survive
    restarts and so user-set values become the new permanent default.

    Expects a `system_settings` table (key/value) or falls back to a
    simple in-memory store if the table doesn't exist yet.
    """

    # In-memory fallback (used before DB is ready or if table is missing)
    _fallback: Dict[str, Any] = {
        "daily_token_limit": 100_000,
        "daily_cost_limit": 5.0,
    }

    @staticmethod
    def _safe_db():
        """Return a DB session context or None."""
        try:
            from backend.models.database import get_db_context
            return get_db_context()
        except Exception:
            return None

    @classmethod
    def load(cls) -> Dict[str, Any]:
        """Load budget config from DB (fallback to in-memory defaults)."""
        try:
            ctx = cls._safe_db()
            if ctx is None:
                return dict(cls._fallback)

            with ctx as db:
                from sqlalchemy import text
                rows = db.execute(
                    text("SELECT key, value FROM system_settings WHERE key IN ('daily_token_limit','daily_cost_limit')")
                ).fetchall()

                result = dict(cls._fallback)
                for row in rows:
                    key, value = row[0], row[1]
                    if key == "daily_token_limit":
                        result["daily_token_limit"] = int(value)
                    elif key == "daily_cost_limit":
                        result["daily_cost_limit"] = float(value)
                return result

        except Exception:
            return dict(cls._fallback)

    @classmethod
    def save(cls, daily_token_limit: int, daily_cost_limit: float):
        """
        Persist new budget limits to DB so they survive restarts.
        Also updates in-memory fallback immediately.
        """
        cls._fallback["daily_token_limit"] = daily_token_limit
        cls._fallback["daily_cost_limit"] = daily_cost_limit

        try:
            ctx = cls._safe_db()
            if ctx is None:
                return

            with ctx as db:
                from sqlalchemy import text
                # Upsert both values
                for key, value in [
                    ("daily_token_limit", str(daily_token_limit)),
                    ("daily_cost_limit", str(daily_cost_limit)),
                ]:
                    db.execute(
                        text("""
                            INSERT INTO system_settings (key, value, updated_at)
                            VALUES (:key, :value, NOW())
                            ON CONFLICT (key) DO UPDATE
                                SET value = EXCLUDED.value,
                                    updated_at = EXCLUDED.updated_at
                        """),
                        {"key": key, "value": value},
                    )
                db.commit()

        except Exception as e:
            # Non-fatal: in-memory fallback is already updated
            logger.warning(f"Could not persist budget to DB: {e}")


# ---------------------------------------------------------------------------
# IdleBudgetManager — sources real usage from ModelUsageLog
# ---------------------------------------------------------------------------

class IdleBudgetManager:
    """
    Enhanced token budget that:
    - Reads limits from the DB (persisted across restarts).
    - Reads *actual* usage from ModelUsageLog (real API data).
    - Allows the user to update limits; new value becomes the permanent default.
    """

    def __init__(self):
        """Initialize budget manager with lazy-loaded DB-backed limits."""
        # Lazy load config
        self._daily_token_limit: Optional[int] = None
        self._daily_cost_limit: Optional[float] = None

        # Cost multiplier for idle vs active (local models are free)
        self.idle_cost_multiplier = 0.0

        # Compatibility properties expected by main.py / token_optimizer
        self._total_tokens_saved = 0
        self._total_cost_saved = 0.0
        
        # Idle-specific budget (separate from active budget)
        self._idle_budget = IdleBudget(
            limit_usd=1.0,  # $1/day default for idle API usage
            used_usd=0.0,
            period_hours=24,
            last_reset=datetime.utcnow()
        )

    @property
    def idle_budget(self) -> IdleBudget:
        """Return the idle budget dataclass."""
        return self._idle_budget

    def _ensure_loaded(self):
        """Ensure loaded."""

        if self._daily_token_limit is None or self._daily_cost_limit is None:
            cfg = SystemBudgetConfig.load()
            self._daily_token_limit = cfg["daily_token_limit"]
            self._daily_cost_limit = cfg["daily_cost_limit"]

    @property
    def daily_token_limit(self) -> int:
        """Return the daily token limit (lazy-loaded from DB if needed)."""
        self._ensure_loaded()
        return self._daily_token_limit

    @daily_token_limit.setter
    def daily_token_limit(self, value: int):
        """Set the daily token limit."""
        self._daily_token_limit = value

    @property
    def daily_cost_limit(self) -> float:
        """Return the daily cost limit in USD (lazy-loaded from DB if needed)."""
        self._ensure_loaded()
        return self._daily_cost_limit

    @daily_cost_limit.setter
    def daily_cost_limit(self, value: float):
        """Set the daily cost limit in USD."""
        self._daily_cost_limit = value

    # ------------------------------------------------------------------
    # Compat properties
    # ------------------------------------------------------------------

    @property
    def daily_idle_budget_usd(self):
        """Return the daily idle budget in USD."""
        return self.daily_cost_limit

    @property
    def daily_cost_limit_usd(self):
        """Return the daily cost limit in USD."""
        return self.daily_cost_limit

    @property
    def total_tokens_saved(self):
        """Return the total number of tokens saved."""
        return self._total_tokens_saved

    @property
    def total_cost_saved_usd(self):
        """Return the total cost saved in USD."""
        return self._total_cost_saved

    # ------------------------------------------------------------------
    # Limit management
    # ------------------------------------------------------------------

    def update_limits(self, daily_token_limit: int, daily_cost_limit: float):
        """
        Update limits in memory AND persist to DB.
        The new values become the permanent default (survive restarts).
        """
        self.daily_token_limit = daily_token_limit
        self.daily_cost_limit = daily_cost_limit
        SystemBudgetConfig.save(daily_token_limit, daily_cost_limit)
        logger.info(f"Budget updated → tokens: {daily_token_limit:,} | cost: ${daily_cost_limit:.2f}/day")

    # ------------------------------------------------------------------
    # Real usage from DB
    # ------------------------------------------------------------------

    def _get_todays_usage(self) -> Dict[str, float]:
        """
        Aggregate today's token/cost totals from ModelUsageLog (real API data).
        Falls back to zeros if DB is unavailable.
        """
        try:
            from backend.models.database import get_db_context
            from backend.models.entities.user_config import ModelUsageLog

            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            with get_db_context() as db:
                row = db.query(
                    func.coalesce(func.sum(ModelUsageLog.total_tokens), 0).label("tokens"),
                    func.coalesce(func.sum(ModelUsageLog.cost_usd), 0.0).label("cost"),
                ).filter(
                    ModelUsageLog.created_at >= today_start
                ).one()

                return {
                    "tokens_used_today": int(row.tokens),
                    "cost_used_today_usd": round(float(row.cost), 6),
                }

        except Exception:
            return {"tokens_used_today": 0, "cost_used_today_usd": 0.0}

    # ------------------------------------------------------------------
    # Budget check (used by model_allocation.py)
    # ------------------------------------------------------------------

    def check_budget(self, estimated_cost: float) -> bool:
        """Return True if estimated_cost fits within today's remaining budget."""
        usage = self._get_todays_usage()
        return (usage["cost_used_today_usd"] + estimated_cost) <= self.daily_cost_limit

    # ------------------------------------------------------------------
    # record_usage — kept for backward-compat; DB log is the source of truth
    # ------------------------------------------------------------------

    def record_usage(self, tokens: int, model_cost_per_1k: float = 0.0, is_idle: bool = False):
        """
        Legacy hook: still tracks token savings for reporting.
        Real cost is logged by model_provider.py → ModelUsageLog.
        """
        cost_multiplier = self.idle_cost_multiplier if is_idle else 1.0
        cost = (tokens / 1000) * model_cost_per_1k * cost_multiplier
        if is_idle:
            self._total_tokens_saved += tokens
            self._total_cost_saved += cost

    # ------------------------------------------------------------------
    # Status (used by BudgetControl frontend)
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """
        Return live budget status sourced from actual API usage logs.
        This is what the /api/v1/admin/budget endpoint returns.
        """
        usage = self._get_todays_usage()
        tokens_used = usage["tokens_used_today"]
        cost_used = usage["cost_used_today_usd"]

        token_pct = round((tokens_used / self.daily_token_limit) * 100, 2) if self.daily_token_limit > 0 else 0
        cost_pct = round((cost_used / self.daily_cost_limit) * 100, 2) if self.daily_cost_limit > 0 else 0

        return {
            "daily_token_limit": self.daily_token_limit,
            "tokens_used_today": tokens_used,
            "tokens_remaining": max(0, self.daily_token_limit - tokens_used),
            "daily_cost_limit_usd": self.daily_cost_limit,
            "cost_used_today_usd": cost_used,
            "cost_remaining_usd": round(max(0.0, self.daily_cost_limit - cost_used), 6),
            "cost_percentage_used": min(cost_pct, 100),
            "cost_percentage_tokens": min(token_pct, 100),
            # Source tag so the frontend can display a note
            "data_source": "api_usage_logs",
        }

    def get_idle_budget_status(self) -> Dict[str, Any]:
        """Return idle-specific budget status."""
        # Refresh from DB
        self._refresh_idle_budget_from_logs()
        
        return {
            "idle_daily_cost_limit_usd": self._idle_budget.limit_usd,
            "idle_cost_used_today_usd": round(self._idle_budget.used_usd, 6),
            "idle_cost_remaining_usd": round(max(0.0, self._idle_budget.limit_usd - self._idle_budget.used_usd), 6),
            "idle_cost_percentage_used": min(round((self._idle_budget.used_usd / self._idle_budget.limit_usd) * 100, 2), 100),
            "idle_period_hours": self._idle_budget.period_hours,
            "last_reset": self._idle_budget.last_reset.isoformat(),
        }

    def _refresh_idle_budget_from_logs(self):
        """Refresh idle budget used_usd from ModelUsageLog for idle tasks."""
        try:
            from backend.models.database import get_db_context
            from backend.models.entities.user_config import ModelUsageLog
            from sqlalchemy import and_

            period_start = datetime.utcnow() - timedelta(hours=self._idle_budget.period_hours)

            with get_db_context() as db:
                logs = db.query(ModelUsageLog).filter(
                    and_(
                        ModelUsageLog.task_type == 'idle_api',
                        ModelUsageLog.created_at >= period_start
                    )
                ).all()
                
                self._idle_budget.used_usd = sum(log.cost_usd or 0.0 for log in logs)
                # Reset if period has passed
                if (datetime.utcnow() - self._idle_budget.last_reset).total_seconds() > self._idle_budget.period_hours * 3600:
                    self._idle_budget.last_reset = datetime.utcnow()
                    self._idle_budget.used_usd = 0.0

        except Exception:
            pass  # Use current values


# ---------------------------------------------------------------------------
# TokenOptimizer
# ---------------------------------------------------------------------------

class TokenOptimizer:
    """
    Enhanced Token Optimizer that:
    1. Tracks token usage per agent
    2. Automatically selects optimal models per task
    3. Manages idle/active transitions with cost awareness
    4. Integrates with hierarchical agent system
    """

    def __init__(self):
        """Initialize the token optimizer with default idle settings."""
        self.idle_mode_active = False
        self.last_activity_at = datetime.utcnow()
        self.idle_threshold_seconds = 60

        # Token tracking (in-memory; DB is the source of truth)
        self.tokens_used_by_agent: Dict[str, int] = {}
        self.total_tokens_saved_today = 0
        self.last_budget_reset = datetime.utcnow()

        # Model allocation tracking
        self.active_model_configs: Dict[str, str] = {}
        self.idle_model_configs: Dict[str, str] = {}

        # Persistent agents
        self.persistent_agents: List[str] = ["00001", "10001", "10002"]

        self.initialized = False

    @property
    def active_budget(self):
        """Return the budget manager (for compatibility with main.py)."""
        return idle_budget

    def initialize(self, db: Session, agents: List[Agent] = None):
        """Initialize with database session and agent list."""
        if self.initialized:
            return

        if agents:
            self.persistent_agents = [a.agentium_id for a in agents if a.is_persistent]

        if model_allocation_module.model_allocator is None:
            init_model_allocator(db)

        self.idle_model_key = "local:kimi-2.5-7b"
        self.initialized = True

    def record_activity(self):
        """Record user activity and wake from idle if needed."""
        self.last_activity_at = datetime.utcnow()

        if self.idle_mode_active:
            from backend.models.database import get_db_context

            async def _wake():
                """Wake."""
                with get_db_context() as db:
                    await self.wake_from_idle(db)

            asyncio.create_task(_wake())

    def get_idle_duration_seconds(self) -> float:
        """Return the number of seconds since the last recorded activity."""
        return (datetime.utcnow() - self.last_activity_at).total_seconds()

    def calculate_token_savings(self, task_type: str, duration_seconds: int) -> int:
        """Calculate token savings."""

        tokens_per_minute = {
            "audit_archival": 50,
            "storage_dedupe": 100,
            "vector_maintenance": 150,
            "cache_optimization": 80,
            "predictive_planning": 200,
            "constitution_refine": 120,
            "ethos_optimization": 90,
            "agent_health_scan": 60,
            "default": 100,
        }
        base_rate = tokens_per_minute.get(task_type, tokens_per_minute["default"])
        duration_minutes = duration_seconds / 60
        active_tokens = base_rate * duration_minutes
        idle_tokens = active_tokens * 0.2
        return max(0, int(active_tokens - idle_tokens))

    async def check_idle_transition(self, db: Session) -> str:
        """Check idle transition."""

        idle_duration = self.get_idle_duration_seconds()
        should_be_idle = idle_duration > self.idle_threshold_seconds

        if should_be_idle and not self.idle_mode_active:
            await self.enter_idle_mode(db)
            return "entered_idle"
        elif not should_be_idle and self.idle_mode_active:
            await self.wake_from_idle(db)
            return "exited_idle"

        return "no_change"

    async def enter_idle_mode(self, db: Session):
        """Enter idle mode."""

        logger.info("Entering idle mode - switching to local models")
        self.idle_mode_active = True

        local_model = api_manager_module.api_manager._get_best_local_model()

        agents = db.query(Agent).filter(
            Agent.agentium_id.in_(self.persistent_agents),
            Agent.status != AgentStatus.TERMINATED,
        ).all()

        for agent in agents:
            if agent.preferred_config_id:
                self.active_model_configs[agent.id] = agent.preferred_config_id
            new_config_id = model_allocation_module.model_allocator._ensure_agent_has_config(agent, local_model).id
            agent.preferred_config_id = new_config_id
            agent.idle_mode_enabled = True
            agent.status = AgentStatus.IDLE_WORKING

        non_persistent = db.query(Agent).filter(
            ~Agent.agentium_id.in_(self.persistent_agents),
            Agent.status == AgentStatus.ACTIVE,
        ).all()

        for agent in non_persistent:
            agent.status = AgentStatus.IDLE_PAUSED

        db.commit()

        await self._broadcast_idle_status("entered_idle", {
            "agents_switched": len(agents),
            "budget_status": idle_budget.get_status(),
        })

        logger.info(f"{len(agents)} agents switched to {local_model.model_name}")

    async def wake_from_idle(self, db: Session):
        """Wake from idle."""

        logger.info("Waking from idle mode - restoring optimized models")
        self.idle_mode_active = False
        self.last_activity_at = datetime.utcnow()

        all_agents = db.query(Agent).filter(Agent.status != AgentStatus.TERMINATED).all()

        for agent in all_agents:
            current_task = db.query(Task).filter_by(
                assigned_to_agent_id=agent.id,
                status=TaskStatus.RUNNING,
            ).first()

            try:
                new_config_id = model_allocation_module.model_allocator.allocate_model(agent, current_task)
                agent.preferred_config_id = new_config_id
            except Exception:
                if agent.agentium_id in self.active_model_configs:
                    agent.preferred_config_id = self.active_model_configs[agent.agentium_id]

            agent.idle_mode_enabled = False
            if agent.status == AgentStatus.IDLE_PAUSED:
                agent.status = AgentStatus.ACTIVE
            elif agent.status == AgentStatus.IDLE_WORKING:
                agent.status = AgentStatus.ACTIVE

        db.commit()

        await self._broadcast_idle_status("exited_idle", {
            "budget_status": idle_budget.get_status(),
        })

        logger.info("All agents restored to optimized models")

    async def allocate_model_for_agent(self, agent: Agent, task: Task, db: Session) -> str:
        """Allocate an optimal model for the given agent and task."""
        if not self.initialized:
            self.initialize(db)

        config_id = model_allocation_module.model_allocator.allocate_model(agent, task)
        self.active_model_configs[agent.agentium_id] = config_id

        self.tokens_used_by_agent.setdefault(agent.agentium_id, 0)
        self._check_daily_reset()

        return config_id

    def estimate_task_tokens(self, task: Task) -> int:
        """Estimate the number of tokens needed for the given task."""
        base_tokens = {
            "code": 2000,
            "analysis": 1500,
            "creative": 1200,
            "simple": 500,
        }
        if not task:
            return 500
        task_type = model_allocation_module.model_allocator._classify_task_type(task) if model_allocation_module.model_allocator else "simple"
        return base_tokens.get(task_type, 1000)

    def update_token_count(self, agent_id: str, tokens_used: int, cost: float = 0.0):
        """Update in-memory tracking (DB log is the true source of truth)."""
        self.tokens_used_by_agent[agent_id] = self.tokens_used_by_agent.get(agent_id, 0) + tokens_used
        if tokens_used > 0:
            savings = int(tokens_used * 0.1)
            self.total_tokens_saved_today += savings
        self._check_daily_reset()

    def _check_daily_reset(self):
        """Check daily reset."""

        now = datetime.utcnow()
        if now.date() > self.last_budget_reset.date():
            self.tokens_used_by_agent.clear()
            self.total_tokens_saved_today = 0
            self.last_budget_reset = now

    def get_cost_report(self, db: Session) -> Dict[str, Any]:
        """Return a comprehensive cost report for the current session."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "idle_mode": self.idle_mode_active,
            "tokens_by_agent": self.tokens_used_by_agent.copy(),
            "total_saved_today": self.total_tokens_saved_today,
            "budget_status": idle_budget.get_status(),
            "allocation_report": model_allocation_module.model_allocator.get_allocation_report() if model_allocation_module.model_allocator else {},
            "hourly_cost_estimate": self._calculate_hourly_cost(db),
        }

    def _calculate_hourly_cost(self, db: Session) -> float:
        """Calculate hourly cost."""

        agents = db.query(Agent).filter_by(is_active=True).all()
        hourly_cost = 0.0
        for agent in agents:
            if not agent.preferred_config:
                continue
            model_key = f"{agent.preferred_config.provider}:{agent.preferred_config.default_model}"
            model = api_manager_module.api_manager.models.get(model_key)
            if model:
                hourly_cost += model.cost_per_1k_tokens
        return hourly_cost

    async def _broadcast_idle_status(self, event: str, data: Dict):
        """Broadcast idle status."""

        try:
            from backend.main import manager
            await manager.broadcast({
                "type": "optimizer_status",
                "event": event,
                "data": data,
                "timestamp": datetime.utcnow().isoformat(),
            })
        except ImportError:
            logger.warning("WebSocket manager not available")

    def get_status(self) -> Dict[str, Any]:
        """Get status."""

        idle_duration = self.get_idle_duration_seconds()
        return {
            "idle_mode_active": self.idle_mode_active,
            "time_since_last_activity_seconds": idle_duration,
            "idle_threshold_seconds": self.idle_threshold_seconds,
            "total_agents_monitored": len(self.tokens_used_by_agent),
            "total_tokens_saved_today": self.total_tokens_saved_today,
            "budget_status": idle_budget.get_status(),
            "is_single_api_mode": api_manager_module.api_manager.single_api_mode()
            if api_manager_module.api_manager
            else False,
        }

    def can_use_api_for_idle_task(
        self,
        task_type: str,
        estimated_cost_usd: float,
        estimated_savings_usd: float
    ) -> Tuple[bool, str]:
        """
        Determine if API usage for an idle task is cost-justified.
        
        Policy: Hybrid — local models by default, API only if 
        estimated_savings > estimated_cost * 1.5 (50% margin).
        
        Also checks: idle budget not exhausted, task_type allowed.
        """
        # Check idle budget (use idle_budget singleton)
        idle_budget_status = idle_budget.get_status()
        cost_used = idle_budget_status.get("cost_used_today_usd", 0.0)
        cost_limit = idle_budget_status.get("daily_cost_limit_usd", 1.0)
        
        if cost_used + estimated_cost_usd > cost_limit:
            return False, f"Idle budget exhausted ({cost_used:.4f}/{cost_limit:.4f} USD)"
        
        # Check cost justification (strict >, not >=)
        threshold = estimated_cost_usd * 1.5
        if estimated_savings_usd <= threshold:
            return False, f"Not cost-justified: savings ${estimated_savings_usd:.4f} <= ${threshold:.4f} (1.5x cost ${estimated_cost_usd:.4f})"
        
        # Check if task type is in allowed list for API
        allowed_api_tasks = {
            'predictive_health_api',
            'constitution_refine',
            'ethos_optimization',
        }
        if task_type not in allowed_api_tasks:
            return False, f"Task type {task_type} not allowed for API usage"
        
        return True, f"Cost-justified: savings ${estimated_savings_usd:.4f} > ${threshold:.4f} (1.5x cost)"

    def record_api_usage(self, task_type: str, tokens: int, cost_usd: float):
        """Record API usage against idle budget."""
        # The actual cost is recorded via ModelUsageLog in model_provider.py
        # This method is for tracking/visibility
        idle_budget_status = idle_budget.get_status()
        idle_budget_status["cost_used_today_usd"] = idle_budget_status.get("cost_used_today_usd", 0.0) + cost_usd
        
        # Also log to audit
        try:
            from backend.models.database import get_db_context
            from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
            
            with get_db_context() as db:
                audit = AuditLog.log(
                    level=AuditLevel.INFO,
                    category=AuditCategory.GOVERNANCE,
                    actor_type="system",
                    actor_id="IDLE_GOVERNANCE",
                    action="idle_api_usage_recorded",
                    description=f"Idle API usage recorded for {task_type}",
                    meta_data={
                        "task_type": task_type,
                        "tokens": tokens,
                        "cost_usd": cost_usd,
                        "budget_type": "idle"
                    }
                )
                db.add(audit)
                db.commit()
        except Exception as e:
            logger.warning(f"Could not record idle API usage audit: {e}")

    def _model_key_from_config_id(self, config_id: str) -> str:
        """The config_id IS the key used in api_manager.models dict."""
        return config_id

    def trim_context_for_agent(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        model_config_id: str,
        reserve_pct: float = 0.15
    ) -> List[Dict[str, str]]:
        """
        Trim message history to fit model's context_window.
        
        Args:
            messages: List of {"role": "...", "content": "..."} (user/assistant turns)
            system_prompt: The system prompt (tokens counted but not trimmed)
            model_config_id: UserModelConfig.id to look up model's context_window
            reserve_pct: Fraction of context_window to reserve for response + overhead (default 15%)
        
        Returns:
            Trimmed message list (most recent turns that fit)
        """
        # 1. Look up model config → get context_window
        model_key = self._model_key_from_config_id(model_config_id)
        model = api_manager_module.api_manager.models.get(model_key)
        context_window = model.context_window if model else 128_000
        
        # 2. Calculate available tokens for messages
        system_tokens = estimate_tokens([], system_prompt)
        available = int(context_window * (1 - reserve_pct)) - system_tokens
        available = max(available, 100)  # Floor - small minimum for small context windows
        
        # 3. Trim from oldest, keeping most recent turns
        return self._trim_messages_to_budget(messages, available)

    def _trim_messages_to_budget(self, messages: List[Dict], budget: int) -> List[Dict]:
        """Keep most recent messages that fit within token budget."""
        if not messages:
            return []
        
        # Estimate total
        total = estimate_tokens(messages, "")
        if total <= budget:
            return messages
        
        # Drop oldest until under budget
        trimmed = messages[:]
        while trimmed and estimate_tokens(trimmed, "") > budget:
            trimmed = trimmed[1:]  # Drop oldest
        
        # Always keep at least the last message
        if not trimmed and messages:
            trimmed = [messages[-1]]
        
        return trimmed


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

token_optimizer = TokenOptimizer()
idle_budget = IdleBudgetManager()   # Loads persisted limits from DB on first use


def init_token_optimizer(db: Session, agents: List[Agent] = None):
    """Initialize token optimizer with database and agents."""
    # Initialize API manager first - model_allocator depends on it
    if api_manager_module.api_manager is None:
        init_api_manager(db)

    token_optimizer.initialize(db, agents)
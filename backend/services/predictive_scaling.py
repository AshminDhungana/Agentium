import os
import time
import json
import logging
from datetime import datetime, timedelta
import pytz
import redis
from sqlalchemy.orm import Session

from backend.models.entities.task import Task, TaskStatus, TaskPriority
from backend.models.entities.agents import Agent, AgentStatus, HeadOfCouncil
from backend.models.entities.audit import AuditLog, AuditCategory, AuditLevel
from backend.services.reincarnation_service import ReincarnationService
from backend.services.token_optimizer import token_optimizer

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# ── Keys ──────────────────────────────────────────────────────────────────────
SCALING_METRICS_KEY = "agentium:scaling:metrics"
BUDGET_EXCEEDED_WS_EVENT = "budget_exceeded"
SCALING_WS_EVENT = "scaling_event"


class PredictiveScalingService:
    @staticmethod
    def snapshot_metrics(db: Session):
        """
        Snapshot current metrics to Redis sorted set.
        Retain 7 days, auto-trim.
        """
        now = int(time.time())
        
        pending_count = db.query(Task).filter(
            Task.status.in_([
                TaskStatus.PENDING,
                TaskStatus.DELIBERATING,
                TaskStatus.APPROVED,
                TaskStatus.ASSIGNED
            ]),
            Task.is_active == True
        ).count()
        
        active_agent_count = db.query(Agent).filter(
            Agent.status.in_([AgentStatus.ACTIVE, AgentStatus.WORKING])
        ).count()
        
        # Calculate avg task duration for tasks completed in last 5m
        five_mins_ago = datetime.utcnow() - timedelta(minutes=5)
        recent_tasks = db.query(Task).filter(
            Task.status == TaskStatus.COMPLETED,
            Task.completed_at >= five_mins_ago
        ).all()
        
        avg_duration = 0
        if recent_tasks:
            durations = [(t.completed_at - t.created_at).total_seconds() for t in recent_tasks if t.completed_at and t.created_at]
            if durations:
                avg_duration = sum(durations) / len(durations)
                
        # Get token spend (we can interface with TokenOptimizer)
        token_spend_last_5m = 0.0
        status = token_optimizer.get_status()
        # Fallback to daily used if we don't have exactly 5m isolate
        token_spend_last_5m = status.get('budget_status', {}).get('cost_used_today_usd', 0.0)
        
        metric_data = {
            "timestamp": now,
            "pending_task_count": pending_count,
            "active_agent_count": active_agent_count,
            "avg_task_duration_seconds": avg_duration,
            "token_spend_last_5m": token_spend_last_5m
        }
        
        # Add to sorted set (score = timestamp)
        redis_client.zadd(SCALING_METRICS_KEY, {json.dumps(metric_data): now})
        
        # Trim older than 7 days (7 * 24 * 60 * 60 = 604800 seconds)
        cutoff = now - 604800
        redis_client.zremrangebyscore(SCALING_METRICS_KEY, 0, cutoff)
        
        logger.info(f"PredictiveScaling: snapshotted metrics: {metric_data}")
        return metric_data


    @staticmethod
    def get_predictions() -> dict:
        """
        Load Predictor: weighted moving average [0.5, 0.3, 0.2] over time-series.
        Output: next_1h, next_6h, next_24h predictions for active agent capacity needs.
        """
        now = int(time.time())
        # Let's get metrics from the last 24h
        cutoff_24h = now - 86400
        data = redis_client.zrangebyscore(SCALING_METRICS_KEY, cutoff_24h, now)
        
        if not data:
            return {"next_1h": 0, "next_6h": 0, "next_24h": 0, "current_capacity": 0, "recommendation": "neutral"}
            
        parsed = [json.loads(d) for d in data]
        
        # We need recent loads. Let's group by 1h, 6h, 24h averages
        # To simplify, we'll take the weighted average of the most recent data points.
        # Latest point = 50%, Previous point = 30%, Point before that = 20%
        
        if len(parsed) >= 3:
            recent_3 = parsed[-3:]
        else:
            recent_3 = parsed
            
        weights = [0.2, 0.3, 0.5] if len(recent_3) == 3 else [1.0 / len(recent_3)] * len(recent_3)
        
        predicted_load = 0.0
        for i, pt in enumerate(recent_3):
            # approximate tasks/hr based on pending + avg duration
            load_heuristic = pt['pending_task_count'] + (pt['active_agent_count'] * 0.5)
            predicted_load += load_heuristic * weights[i]
            
        current_capacity = parsed[-1]['active_agent_count']
        
        # A simple projection for next_1h, next_6h, next_24h
        next_1h = predicted_load * 1.2
        next_6h = predicted_load * 1.5
        next_24h = predicted_load * 1.1

        recommendation = "neutral"
        if next_1h > current_capacity * 0.8:
            recommendation = "spawn"
        elif next_6h < current_capacity * 0.3:
            recommendation = "liquidate"

        return {
            "next_1h": round(next_1h, 2),
            "next_6h": round(next_6h, 2),
            "next_24h": round(next_24h, 2),
            "current_capacity": current_capacity,
            "recommendation": recommendation
        }

    @staticmethod
    def evaluate_scaling(db: Session, predictions: dict):
        """
        Pre-Spawn Decision: if next_1h_prediction > current_capacity * 0.8
        Pre-Liquidation: if next_6h_prediction < current_capacity * 0.3
        """
        current_capacity = predictions["current_capacity"]
        next_1h = predictions["next_1h"]
        next_6h = predictions["next_6h"]
        
        head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        if not head:
            return
            
        # ── Time-Based Policy ─────────────────────────────────────────────────
        tz_str = os.getenv("BUSINESS_HOURS_TZ", "UTC")
        start_hour = int(os.getenv("BUSINESS_HOURS_START", "9"))
        end_hour = int(os.getenv("BUSINESS_HOURS_END", "17"))
        
        tz = pytz.timezone(tz_str)
        local_time = datetime.now(tz)
        local_hour = local_time.hour
        
        is_business_hours = (start_hour <= local_hour < end_hour)
        if not is_business_hours:
            # outside hours, cap active task agents at 2
            if current_capacity >= 2 and predictions["recommendation"] == "spawn":
                logger.info("PredictiveScaling: Outside Business Hours. Capping active task agents spawn.")
                return

        # ── Pre-Spawn ─────────────────────────────────────────────────────────
        if next_1h > current_capacity * 0.8 and current_capacity < 50:
            recommended_spawn = max(1, int((next_1h - current_capacity) / 2))
            logger.info(f"PredictiveScaling: next_1h ({next_1h}) > 80% capacity ({current_capacity}). Spawning {recommended_spawn}.")
            
            spawned = 0
            for i in range(recommended_spawn):
                try:
                    ReincarnationService.spawn_task_agent(
                        parent=head,
                        name=f"Predictive-Spawn-{datetime.utcnow().strftime('%H%M%S')}-{i}",
                        description="Pre-spawned by Predictive Auto-Scaler to absorb forecasted load surge.",
                        db=db
                    )
                    spawned += 1
                except Exception as exc:
                    logger.error(f"PredictiveScaling: spawn failed: {exc}")
                    
            entry = AuditLog.log(
                level=AuditLevel.INFO,
                category=AuditCategory.GOVERNANCE,
                actor_type="system",
                actor_id="Predictive Auto-Scaler",
                action="auto_scale_predictive_spawn",
                description=f"Predictive scale spawned {spawned} agents.",
                after_state={"next_1h": next_1h, "spawned": spawned}
            )
            if isinstance(entry, AuditLog):
                db.add(entry)
                db.commit()
            # Emit WebSocket Event
            from backend.api.routes.websocket import manager
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(manager.broadcast({"type": SCALING_WS_EVENT, "action": "spawn", "count": spawned}))
            except Exception:
                pass


        # ── Pre-Liquidation ───────────────────────────────────────────────────
        elif next_6h < current_capacity * 0.3 and current_capacity > 2:
            logger.info(f"PredictiveScaling: next_6h ({next_6h}) < 30% capacity ({current_capacity}). Liquidating idle agents.")
            # find idle agents > 30 min
            idle_cutoff = datetime.utcnow() - timedelta(minutes=30)
            idle_agents = db.query(Agent).filter(
                Agent.status == AgentStatus.IDLE,
                Agent.last_active < idle_cutoff,
                Agent.is_persistent == False
            ).limit(2).all()
            
            liquidated = 0
            for ag in idle_agents:
                ag.is_active = False
                ag.status = AgentStatus.TERMINATED
                liquidated += 1
                
            db.commit()
            
            if liquidated > 0:
                entry = AuditLog.log(
                    level=AuditLevel.INFO,
                    category=AuditCategory.GOVERNANCE,
                    actor_type="system",
                    actor_id="Predictive Auto-Scaler",
                    action="auto_scale_predictive_liquidate",
                    description=f"Predictive scale liquidated {liquidated} idle agents.",
                    after_state={"next_6h": next_6h, "liquidated": liquidated}
                )
                if isinstance(entry, AuditLog):
                    db.add(entry)
                    db.commit()
                from backend.api.routes.websocket import manager
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(manager.broadcast({"type": SCALING_WS_EVENT, "action": "liquidate", "count": liquidated}))
                except Exception:
                    pass


    @staticmethod
    def enforce_token_budget_guard(db: Session):
        """
        Token Budget Guard: default $10.00
        At 80% downgrade new allocations (handled by allocator in reality, but we note it).
        At 100% pause non-CRITICAL.
        """
        budget_limit = float(os.getenv("DAILY_TOKEN_BUDGET_USD", "10.00"))
        
        status = token_optimizer.get_status()
        used = float(status.get('budget_status', {}).get('cost_used_today_usd', 0.0))
        
        if used >= budget_limit:
            # Emits budget_exceeded WS
            from backend.api.routes.websocket import manager
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(manager.broadcast({"type": BUDGET_EXCEEDED_WS_EVENT, "used": used, "limit": budget_limit}))
            except Exception:
                pass
                
            logger.warning(f"PredictiveScaling: Token Budget Exceeded: ${used:.2f} / ${budget_limit:.2f}")
            # Pause non-critical tasks
            active_tasks = db.query(Task).filter(
                Task.status.in_([TaskStatus.IN_PROGRESS, TaskStatus.PENDING]),
                Task.priority.not_in([TaskPriority.CRITICAL, TaskPriority.SOVEREIGN])
            ).all()
            
            for t in active_tasks:
                t.status = TaskStatus.PAUSED
                if t.execution_context is None:
                    t.execution_context = {}
                t.execution_context["pause_reason"] = "Token Budget Exceeded"
                
            db.commit()
            
        elif used >= budget_limit * 0.8:
            logger.info(f"PredictiveScaling: Token Budget Warning: ${used:.2f} / ${budget_limit:.2f}")
            # The model allocator should see this via its own logic or we inject a variable.
            # In Phase 13.3 we just note the warning and maybe set a redis flag
            redis_client.set("agentium:budget:warning", "true", ex=86400)
        else:
            redis_client.delete("agentium:budget:warning")

predictive_scaling_service = PredictiveScalingService()
"""
Token Optimization Service for Agentium IDLE GOVERNANCE.
Dynamically switches between API models (active) and Local models (idle).
"""

import asyncio
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from backend.models.entities.agents import Agent, HeadOfCouncil, CouncilMember, AgentStatus
from backend.models.entities.user_config import UserModelConfig, ProviderType


class TokenOptimizer:
    """
    Optimizes token usage by switching to local models during idle periods.
    Maintains separate configurations for Active vs Idle modes.
    """
    
    def __init__(self):
        self.idle_mode_active = False
        self.last_activity_at = datetime.utcnow()
        self.idle_threshold_seconds = 60  # Switch to idle after 60s of inactivity
        self.persistent_agents: List[str] = []  # Agentium IDs
        self.active_configs: Dict[str, str] = {}  # agent_id -> config_id
        self.idle_configs: Dict[str, str] = {}    # agent_id -> local_config_id
        self.total_tokens_saved = 0
    
    def record_activity(self):
        """Call this whenever user activity occurs."""
        self.last_activity_at = datetime.utcnow()
        if self.idle_mode_active:
            asyncio.create_task(self.wake_from_idle())
    
    async def check_idle_transition(self, db: Session) -> bool:
        """
        Check if system should transition to/from idle mode.
        Returns True if state changed.
        """
        idle_duration = (datetime.utcnow() - self.last_activity_at).total_seconds()
        should_be_idle = idle_duration > self.idle_threshold_seconds
        
        if should_be_idle and not self.idle_mode_active:
            await self.enter_idle_mode(db)
            return True
        elif not should_be_idle and self.idle_mode_active:
            await self.wake_from_idle(db)
            return True
        
        return False
    
    async def enter_idle_mode(self, db: Session):
        """Switch persistent agents to local model configurations."""
        print("🌙 Entering IDLE MODE - Switching to local models")
        self.idle_mode_active = True
        
        # Get or create local model config
        local_config = self._get_or_create_local_config(db)
        
        # Switch persistent agents to local config
        persistent_agents = db.query(Agent).filter_by(
            is_persistent=True,
            is_active='Y'
        ).all()
        
        for agent in persistent_agents:
            # Store active config
            if agent.preferred_config_id:
                self.active_configs[agent.id] = agent.preferred_config_id
            
            # Switch to idle config
            agent.preferred_config_id = local_config.id
            agent.idle_mode_enabled = True
            agent.status = AgentStatus.IDLE_WORKING
            
            # Update persistent agents list
            if agent.agentium_id not in self.persistent_agents:
                self.persistent_agents.append(agent.agentium_id)
        
        db.commit()
        
        # Broadcast status via WebSocket (if available)
        await self._broadcast_idle_status("entered_idle", {
            'agents_switched': len(persistent_agents),
            'total_tokens_saved': self.total_tokens_saved
        })
        
        print(f"✅ {len(persistent_agents)} agents switched to local models")
    
    async def wake_from_idle(self, db: Session):
        """Wake system from idle mode - switch back to API models."""
        print("☀️ Waking from IDLE MODE - Restoring API models")
        self.idle_mode_active = False
        self.last_activity_at = datetime.utcnow()
        
        # Restore original configs
        for agent_id, config_id in self.active_configs.items():
            agent = db.query(Agent).filter_by(id=agent_id).first()
            if agent:
                agent.preferred_config_id = config_id
                agent.idle_mode_enabled = False
                agent.status = AgentStatus.ACTIVE
        
        # Clear idle configs
        self.idle_configs.clear()
        
        # Pause any running idle tasks
        self._pause_idle_tasks(db)
        
        db.commit()
        
        await self._broadcast_idle_status("exited_idle", {
            'agents_restored': len(self.active_configs),
            'total_tokens_saved': self.total_tokens_saved
        })
        
        self.active_configs.clear()
        print("✅ All agents restored to API models")
    
    def _get_or_create_local_config(self, db: Session) -> UserModelConfig:
        """Get or create the shared local model configuration."""
        # Check if shared local config exists
        local_config = db.query(UserModelConfig).filter_by(
            user_id="system",
            config_name="idle_local_model"
        ).first()
        
        if not local_config:
            # Create local model config
            local_config = UserModelConfig(
                user_id="system",
                config_name="idle_local_model",
                provider=ProviderType.LOCAL,
                api_key_encrypted=None,  # Local models don't need API keys
                default_model="kimi-2.5-7b",  # Default local model
                local_server_url="http://localhost:8000/v1",
                is_default=False,
                status='active'
            )
            db.add(local_config)
            db.flush()
        
        return local_config
    
    def _pause_idle_tasks(self, db: Session):
        """Pause any currently running idle tasks."""
        from backend.models.entities.task import Task, TaskStatus
        
        running_idle_tasks = db.query(Task).filter_by(
            status=TaskStatus.IDLE_RUNNING,
            is_idle_task=True
        ).all()
        
        for task in running_idle_tasks:
            task.pause_for_user_task()
        
        print(f"⏸️ Paused {len(running_idle_tasks)} idle tasks")
    
    def calculate_token_savings(self, agent: Agent, estimation_method: str = "average") -> int:
        """
        Estimate tokens saved by using local model vs API.
        Methods: 'conservative', 'average', 'optimistic'
        """
        # Average token usage per request by model tier
        token_rates = {
            "gpt-4": 2000,        # Average tokens per call
            "gpt-4-turbo": 1500,
            "gpt-3.5-turbo": 800,
            "claude-3-opus": 2500,
            "claude-3-sonnet": 1500,
            "kimi-2.5": 1200,
            "default": 1000
        }
        
        multiplier = {
            "conservative": 0.5,
            "average": 1.0,
            "optimistic": 1.5
        }.get(estimation_method, 1.0)
        
        # Get agent's typical usage
        if agent.preferred_config:
            model = agent.preferred_config.default_model
            base_tokens = token_rates.get(model, token_rates["default"])
        else:
            base_tokens = token_rates["default"]
        
        saved = int(base_tokens * multiplier)
        self.total_tokens_saved += saved
        return saved
    
    async def _broadcast_idle_status(self, event: str, data: Dict):
        """Broadcast idle status changes via WebSocket."""
        # This will be integrated with the ConnectionManager in main.py
        try:
            from backend.main import manager
            await manager.broadcast({
                "type": "idle_status",
                "event": event,
                "data": data,
                "timestamp": datetime.utcnow().isoformat()
            })
        except Exception as e:
            print(f"⚠️ Could not broadcast idle status: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current optimizer status."""
        idle_duration = (datetime.utcnow() - self.last_activity_at).total_seconds()
        
        return {
            "idle_mode_active": self.idle_mode_active,
            "time_since_last_activity_seconds": idle_duration,
            "idle_threshold_seconds": self.idle_threshold_seconds,
            "persistent_agents_count": len(self.persistent_agents),
            "total_tokens_saved": self.total_tokens_saved,
            "agents_in_idle_mode": self.persistent_agents if self.idle_mode_active else []
        }


# Singleton instance
token_optimizer = TokenOptimizer()


class IdleBudgetManager:
    """
    Manages token budget for idle operations.
    Ensures we don't exceed reasonable limits even during idle.
    """
    
    def __init__(self, daily_token_limit: int = 100000):
        self.daily_token_limit = daily_token_limit
        self.tokens_used_today = 0
        self.last_reset = datetime.utcnow()
    
    def check_budget(self, estimated_cost: int) -> bool:
        """Check if operation fits within daily budget."""
        self._check_reset()
        return (self.tokens_used_today + estimated_cost) <= self.daily_token_limit
    
    def record_usage(self, tokens: int):
        """Record token usage."""
        self._check_reset()
        self.tokens_used_today += tokens
    
    def _check_reset(self):
        """Reset counter if it's a new day."""
        now = datetime.utcnow()
        if now.date() > self.last_reset.date():
            self.tokens_used_today = 0
            self.last_reset = now
    
    def get_status(self) -> Dict[str, Any]:
        """Get budget status."""
        self._check_reset()
        return {
            "daily_limit": self.daily_token_limit,
            "used_today": self.tokens_used_today,
            "remaining": self.daily_token_limit - self.tokens_used_today,
            "percentage_used": (self.tokens_used_today / self.daily_token_limit) * 100
        }


# Budget manager instance
idle_budget = IdleBudgetManager(daily_token_limit=50000)  # Conservative 50k/day for idle
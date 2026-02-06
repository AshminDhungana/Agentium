"""
ModelAllocationService - Intelligently assigns models to agents based on tier, task, and available APIs.
Sits between TokenOptimizer and APIManager.
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.models.entities.agents import Agent
from backend.models.entities.task import Task, TaskType, TaskPriority
from backend.models.entities.user_config import UserModelConfig
from backend.services.api_manager import api_manager, ModelCapability, ModelConfig
# from backend.services.token_optimizer import token_optimizer, idle_budget


class ModelAllocationService:
    """
    Service that determines the optimal model for each agent based on:
    - Agent tier (0xxxx, 1xxxx, 2xxxx, 3xxxx)
    - Task type and priority
    - Available API pool
    - Cost constraints
    - Token budget
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.agent_model_cache: Dict[str, str] = {}  # agentium_id -> model_config_id
        
    
    def allocate_model(self, agent: Agent, task: Optional[Task] = None) -> str:
        """
        Main method: Allocate the best model for agent/task.
        Returns the UserModelConfig.id to use.
        
        Policy Matrix:
        ┌───────────┬──────────────┬──────────────┬──────────────┬──────────────┐
        │           │    CODE      │  ANALYSIS    │  CREATIVE    │    SIMPLE    │
        ├───────────┼──────────────┼──────────────┼──────────────┼──────────────┤
        │ Head 0xxxx│ Best API     │ Best API     │ Best API     │ Best API     │
        │ Council   │ Best API     │ High-Quality │ High-Quality │ Balanced     │
        │ Lead 2xxxx│ Best API*    │ Balanced     │ Balanced     │ Budget       │
        │ Task 3xxxx│ Best API*    │ Budget       │ Budget       │ Local/Cache  │
        └───────────┴──────────────┴──────────────┴──────────────┴──────────────┘
        
        *Code tasks override tier restrictions
        """
        
        # CRITICAL: Idle mode always uses local model (lowest cost)
        from backend.services.token_optimizer import token_optimizer
        if token_optimizer.idle_mode_active:
            return self._get_idle_model(agent)
        
        # Get task classification
        task_type = self._classify_task_type(task)
        task_priority = task.priority if task else TaskPriority.NORMAL
        
        # Determine agent tier
        agent_tier = int(agent.agentium_id[0])
        
        # Special case: Code tasks get best model regardless of tier
        if task_type == "code":
            return self._allocate_code_model(agent, task_priority)
        
        # Single API mode: Use the one available API for all
        if api_manager.single_api_mode():
            return self._handle_single_api_mode(agent, task_type)
        
        # Multi-API mode: Optimize based on tier and task
        return self._allocate_tier_aware_model(agent_tier, task_type, task_priority, agent)
    
    def _classify_task_type(self, task: Optional[Task]) -> str:
        """Classify task into type string for model allocation."""
        if not task:
            return "simple"
        
        # Map TaskType enum to our classification
        type_mapping = {
            TaskType.CODE_GENERATION: "code",
            TaskType.CODE_REVIEW: "code",
            TaskType.DEBUGGING: "code",
            TaskType.SYSTEM_ANALYSIS: "analysis",
            TaskType.DECISION: "analysis",
            TaskType.RESEARCH: "analysis",
            TaskType.PLANNING: "analysis",
            TaskType.CREATIVE_WRITING: "creative",
            TaskType.BRAINSTORMING: "creative",
            TaskType.DOCUMENTATION: "creative",
            TaskType.SIMPLE_QUERY: "simple",
            TaskType.CONFIRMATION: "simple",
        }
        
        # Default classification based on description
        if task.task_type in type_mapping:
            return type_mapping[task.task_type]
        
        # Fallback: analyze description
        desc_lower = task.description.lower()
        if any(kw in desc_lower for kw in ['write', 'create', 'story', 'idea']):
            return "creative"
        elif any(kw in desc_lower for kw in ['simple', 'check', 'confirm', 'hello']):
            return "simple"
        elif any(kw in desc_lower for kw in ['analyze', 'plan', 'strategy', 'research']):
            return "analysis"
        
        return "simple"  # Default to simplest/cheapest
    
    def _get_idle_model(self, agent: Agent) -> str:
        """
        Get model for idle operations.
        Always uses cheapest local model available.
        """
        local_model = api_manager._get_best_local_model()
        
        # Ensure agent has this config in DB
        config = self._ensure_agent_has_config(agent, local_model)
        
        # Record token savings
        from backend.services.token_optimizer import token_optimizer, idle_budget
        savings = token_optimizer.calculate_token_savings(agent, "conservative")
        idle_budget.record_usage(savings)  # Track against idle budget
        
        return config.id
    
    def _handle_single_api_mode(self, agent: Agent, task_type: str) -> str:
        """
        When only one API is available, use it for all tasks.
        Creates a shared config if needed.
        """
        available_models = [m for m in api_manager.models.values() if m.is_available]
        if not available_models:
            raise ValueError("No API models available")
        
        single_model = available_models[0]
        config = self._ensure_agent_has_config(agent, single_model)
        return config.id
    
    def _allocate_code_model(self, agent: Agent, priority: TaskPriority) -> str:
        """
        Allocate best model for code tasks regardless of tier.
        Code tasks require highest quality to avoid debugging costs.
        """
        # Get best code model (gpt-4 or claude-3-opus)
        code_model = api_manager._get_best_available_model_by_capability(
            ModelCapability.CODE
        )
        
        # For critical code tasks, ensure we get the absolute best
        if priority == TaskPriority.CRITICAL:
            # Check if we can afford it (budget-wise)
            from backend.services.token_optimizer import idle_budget
            if idle_budget.check_budget(code_model.cost_per_1k_tokens * 10):  # Estimate
                config = self._ensure_agent_has_config(agent, code_model)
                return config.id
        
        config = self._ensure_agent_has_config(agent, code_model)
        return config.id
    
    def _allocate_tier_aware_model(
        self, 
        agent_tier: int, 
        task_type: str, 
        priority: TaskPriority,
        agent: Agent
    ) -> str:
        """
        Allocate model based on agent tier following the policy matrix.
        """
        # Define tier-based capability preferences
        tier_preferences = {
            0: {  # Head: Always best
                "code": ModelCapability.CODE,
                "analysis": ModelCapability.CODE,
                "creative": ModelCapability.CODE,
                "simple": ModelCapability.CODE
            },
            1: {  # Council: High quality for important tasks
                "code": ModelCapability.CODE,
                "analysis": ModelCapability.ANALYSIS,
                "creative": ModelCapability.ANALYSIS,
                "simple": ModelCapability.SIMPLE
            },
            2: {  # Lead: Balanced approach
                "code": ModelCapability.CODE,  # Code override
                "analysis": ModelCapability.ANALYSIS,
                "creative": ModelCapability.CREATIVE,
                "simple": ModelCapability.SIMPLE
            },
            3: {  # Task: Budget-conscious
                "code": ModelCapability.CODE,  # Code override - always best
                "analysis": ModelCapability.SIMPLE,  # Use simple model to save costs
                "creative": ModelCapability.SIMPLE,
                "simple": ModelCapability.SIMPLE
            }
        }
        
        preferences = tier_preferences.get(agent_tier, tier_preferences[3])
        target_capability = preferences.get(task_type, ModelCapability.SIMPLE)
        
        # Priority boost for high-priority tasks
        if priority in [TaskPriority.HIGH, TaskPriority.CRITICAL]:
            # Bump up one capability level
            capability_boost = {
                ModelCapability.SIMPLE: ModelCapability.ANALYSIS,
                ModelCapability.ANALYSIS: ModelCapability.CODE,
                ModelCapability.CREATIVE: ModelCapability.ANALYSIS,
                ModelCapability.CODE: ModelCapability.CODE  # Already max
            }
            target_capability = capability_boost.get(target_capability, target_capability)
        
        # Get model for capability
        model = api_manager._get_best_available_model_by_capability(target_capability)
        
        # Budget check for Task agents (tier 3)
        from backend.services.token_optimizer import idle_budget
        if agent_tier == 3 and not idle_budget.check_budget(model.cost_per_1k_tokens * 5):
            # Over budget, force to local model
            model = api_manager._get_best_local_model()
        
        config = self._ensure_agent_has_config(agent, model)
        return config.id
    
    def _ensure_agent_has_config(self, agent: Agent, model: 'ModelConfig') -> 'UserModelConfig':
        """
        Ensure agent has a UserModelConfig record for this model.
        Creates one if it doesn't exist.
        """
        # Check if agent already has this config
        existing = self.db.query(UserModelConfig).filter_by(
            user_id=agent.id,
            default_model=model.model_name,
            provider=model.provider
        ).first()
        
        if existing:
            return existing
        
        # Create new config for this agent
        config = UserModelConfig(
            user_id=agent.id,
            config_name=f"auto_{model.model_name}_{agent.agentium_id}",
            provider=model.provider,
            api_key_encrypted=None,  # Use shared API key
            default_model=model.model_name,
            base_url=None,
            temperature=0.7 if model.capability != ModelCapability.CODE else 0.2,  # Lower temp for code
            max_tokens=4000,
            is_default=False,
            status='active'
        )
        self.db.add(config)
        self.db.flush()
        
        # Cache the assignment
        self.agent_model_cache[agent.agentium_id] = config.id
        
        return config
    
    def reallocate_model(self, agent: Agent, task: Task) -> bool:
        """
        Reallocate model if task characteristics change mid-execution.
        Returns True if model was changed.
        """
        # Check if we need to upgrade due to task complexity
        current_config = agent.preferred_config
        
        if not current_config:
            return False
        
        new_allocation = self.allocate_model(agent, task)
        
        if current_config.id != new_allocation:
            agent.preferred_config_id = new_allocation
            self.db.commit()
            return True
        
        return False
    
    def get_allocation_report(self) -> Dict[str, Any]:
        """
        Get report of current model allocations across all agents.
        """
        agents = self.db.query(Agent).filter_by(is_active='Y').all()
        
        report = {
            "total_agents": len(agents),
            "allocations_by_tier": {0: 0, 1: 0, 2: 0, 3: 0},
            "allocations_by_capability": {
                cap.value: 0 for cap in ModelCapability
            },
            "estimated_hourly_cost": 0.0,
            "agent_details": []
        }
        
        for agent in agents:
            if not agent.preferred_config:
                continue
            
            tier = int(agent.agentium_id[0])
            model_key = f"{agent.preferred_config.provider}:{agent.preferred_config.default_model}"
            model = api_manager.models.get(model_key)
            
            if not model:
                continue
            
            report["allocations_by_tier"][tier] += 1
            report["allocations_by_capability"][model.capability.value] += 1
            
            # Estimate cost (assuming average 1000 tokens/hour)
            report["estimated_hourly_cost"] += model.cost_per_1k_tokens
            
            report["agent_details"].append({
                "agentium_id": agent.agentium_id,
                "model": model.model_name,
                "capability": model.capability.value,
                "cost_per_1k": model.cost_per_1k_tokens,
                "is_idle": agent.idle_mode_enabled
            })
        
        return report


# Global instance
model_allocator = None

def init_model_allocator(db: Session):
    """Initialize the global ModelAllocationService."""
    global model_allocator
    model_allocator = ModelAllocationService(db)
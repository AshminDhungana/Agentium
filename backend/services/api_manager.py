"""
APIManager - Manages multiple LLM providers and assigns best models per task.
Supports OpenAI, Anthropic, Local Kimi, and custom models.
"""
import logging
import json
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from sqlalchemy.orm import Session
from backend.models.entities.user_config import UserModelConfig
from backend.models.entities.agents import Agent

if TYPE_CHECKING:
    from backend.models.entities.task import Task


logger = logging.getLogger(__name__)
class ModelCapability(Enum):
    """Model capabilities for task matching."""
    CODE = "code"  # Best for programming
    ANALYSIS = "analysis"  # Complex reasoning
    CREATIVE = "creative"  # Writing, ideation
    SIMPLE = "simple"  # Basic Q&A
    IDLE = "idle"  # Low-priority background tasks

@dataclass
class ModelConfig:
    """Configuration for a specific model."""
    provider: str  # openai, anthropic, local, etc.
    model_name: str  # gpt-4, claude-3-opus, kimi-2.5, etc.
    config_id: str  # Internal ID
    cost_per_1k_tokens: float  # USD
    max_context_length: int
    rate_limit_per_minute: int
    capability: ModelCapability
    is_available: bool = True
    current_load: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "config_id": self.config_id,
            "cost_per_1k_tokens": self.cost_per_1k_tokens,
            "max_context_length": self.max_context_length,
            "capability": self.capability.value,
            "is_available": self.is_available,
            "current_load": self.current_load
        }

class APIManager:
    """
    Central manager for all LLM APIs.
    Implements load balancing, health checks, and fallback logic.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.models: Dict[str, ModelConfig] = {}
        self.api_health: Dict[str, bool] = {}
        self._initialize_models()
    
    def _initialize_models(self):
        """Load model configurations from database."""
        configs = self.db.query(UserModelConfig).filter_by(is_active='Y').all()
        
        # Define capabilities and costs for known models
        model_metadata = {
            # OpenAI
            "gpt-4": {"capability": ModelCapability.CODE, "cost": 0.03, "context": 8192},
            "gpt-4-turbo": {"capability": ModelCapability.ANALYSIS, "cost": 0.01, "context": 128000},
            "gpt-3.5-turbo": {"capability": ModelCapability.SIMPLE, "cost": 0.0015, "context": 16385},
            
            # Anthropic
            "claude-3-opus": {"capability": ModelCapability.CODE, "cost": 0.015, "context": 200000},
            "claude-3-sonnet": {"capability": ModelCapability.ANALYSIS, "cost": 0.003, "context": 200000},
            "claude-3-haiku": {"capability": ModelCapability.SIMPLE, "cost": 0.00075, "context": 200000},
            
            # Local - Zero cost, lower performance
            "kimi-2.5": {"capability": ModelCapability.IDLE, "cost": 0.0, "context": 32000},
            "kimi-2.5-7b": {"capability": ModelCapability.IDLE, "cost": 0.0, "context": 32000},
            "llama-2-7b": {"capability": ModelCapability.IDLE, "cost": 0.0, "context": 4096},
            "mistral-7b": {"capability": ModelCapability.IDLE, "cost": 0.0, "context": 8192},
            
            # Default fallback
            "default": {"capability": ModelCapability.SIMPLE, "cost": 0.001, "context": 8000}
        }
        
        for config in configs:
            # Determine capability based on model name or provider
            metadata = model_metadata.get(
                config.default_model, 
                model_metadata["default"]
            )
            
            # Override for local provider
            if config.provider == "local":
                metadata["capability"] = ModelCapability.IDLE
            
            model_key = f"{config.provider}:{config.default_model}"
            self.models[model_key] = ModelConfig(
                provider=config.provider,
                model_name=config.default_model,
                config_id=config.id,
                cost_per_1k_tokens=metadata["cost"],
                max_context_length=metadata["context"],
                rate_limit_per_minute=config.rate_limit or 60,
                capability=metadata["capability"],
                is_available=True
            )
    
    def get_best_model(
        self, 
        task_type: str, 
        agent_tier: int,
        budget_constraint: Optional[float] = None
    ) -> ModelConfig:
        """
        Get best model for task based on:
        - Task type (code, analysis, simple, idle)
        - Agent tier (0=Head, 1=Council, 2=Lead, 3=Task)
        - Budget constraint
        """
        # Map task description to capability
        capability = self._classify_task(task_type)
        
        # Override with best model for code tasks
        if capability == ModelCapability.CODE:
            # Always use best code model regardless of tier
            return self._get_best_available_model_by_capability(ModelCapability.CODE)
        
        # Idle mode: Always return local model
        if capability == ModelCapability.IDLE:
            return self._get_best_local_model()
        
        # Tier-based model selection
        tier_policy = {
            0: self._get_best_available_model_by_capability(ModelCapability.CODE),  # Head: Best of best
            1: self._get_best_available_model_by_capability(ModelCapability.ANALYSIS),  # Council: High quality
            2: self._select_balanced_model(budget_constraint),  # Lead: Balanced cost/performance
            3: self._get_budget_model()  # Task: Cheapest available
        }
        
        return tier_policy.get(agent_tier, self._get_budget_model())
    
    def _classify_task(self, task_description: str) -> ModelCapability:
        """Classify task into capability category."""
        desc_lower = task_description.lower()
        
        # Code task detection
        code_keywords = ['code', 'program', 'function', 'script', 'python', 'javascript', 'debug', 'error', 'exception']
        if any(kw in desc_lower for kw in code_keywords):
            return ModelCapability.CODE
        
        # Analysis task detection
        analysis_keywords = ['analyze', 'reasoning', 'complex', 'strategy', 'planning', 'evaluation']
        if any(kw in desc_lower for kw in analysis_keywords):
            return ModelCapability.ANALYSIS
        
        # Creative task detection
        creative_keywords = ['write', 'create', 'story', 'idea', 'brainstorm', 'design']
        if any(kw in desc_lower for kw in creative_keywords):
            return ModelCapability.CREATIVE
        
        # Simple task detection
        simple_keywords = ['hello', 'hi', 'thanks', 'yes', 'no', 'ok', 'simple', 'basic']
        if any(kw in desc_lower for kw in simple_keywords) and len(desc_lower) < 100:
            return ModelCapability.SIMPLE
        
        # Default to analysis for medium complexity
        return ModelCapability.ANALYSIS
    
    def _get_best_available_model_by_capability(self, capability: ModelCapability) -> ModelConfig:
        """Get highest-rated model for capability."""
        candidates = [
            m for m in self.models.values() 
            if m.capability == capability and m.is_available
        ]
        
        # Sort by capability tier then cost (best first)
        capability_rank = {
            ModelCapability.CODE: 0,
            ModelCapability.ANALYSIS: 1,
            ModelCapability.CREATIVE: 2,
            ModelCapability.SIMPLE: 3,
            ModelCapability.IDLE: 4
        }
        
        candidates.sort(key=lambda m: (
            capability_rank.get(m.capability, 99),
            -m.max_context_length,  # Higher context better
            m.cost_per_1k_tokens    # Lower cost better
        ))
        
        return candidates[0] if candidates else self._get_budget_model()
    
    def _get_best_local_model(self) -> ModelConfig:
        """Get best local model (zero cost)."""
        local_models = [
            m for m in self.models.values() 
            if m.provider == "local" and m.is_available
        ]
        
        # Prefer larger local models
        local_models.sort(key=lambda m: -m.max_context_length)
        
        return local_models[0] if local_models else self._get_budget_model()
    
    def _select_balanced_model(self, budget: Optional[float]) -> ModelConfig:
        """Select model balancing cost and performance."""
        available = [m for m in self.models.values() if m.is_available]
        
        # Apply budget filter if provided
        if budget is not None:
            available = [m for m in available if m.cost_per_1k_tokens <= budget]
        
        if not available:
            return self._get_budget_model()
        
        # Select model with best (capability / cost) ratio
        # Favor cheaper models for budget-conscious operations
        available.sort(key=lambda m: (
            m.cost_per_1k_tokens,  # Lower cost first
            -m.max_context_length  # But higher context within that cost
        ))
        
        return available[0]
    
    def _get_budget_model(self) -> ModelConfig:
        """Get cheapest available model."""
        available = [m for m in self.models.values() if m.is_available]
        available.sort(key=lambda m: m.cost_per_1k_tokens)
        return available[0] if available else list(self.models.values())[0]
    
    def check_api_health(self) -> Dict[str, bool]:
        """Check health of all API providers."""
        # In production, make actual API calls
        # For now, return cached status
        return {name: model.is_available for name, model in self.models.items()}
    
    def update_model_load(self, model_key: str, delta: int):
        """Update current load on a model (for rate limiting)."""
        if model_key in self.models:
            self.models[model_key].current_load += delta
    
    def get_all_models(self) -> Dict[str, ModelConfig]:
        """Get all model configurations."""
        return self.models
    
    def single_api_mode(self) -> bool:
        """Check if only one API is available."""
        active_apis = len(set(m.provider for m in self.models.values() if m.is_available))
        return active_apis == 1
    
    def get_model_for_agent(self, agent: Agent, task: Optional['Task'] = None) -> ModelConfig:
        """
        Get best model for specific agent and optional task.
        This is the main method used by the orchestrator.
        """
        agent_tier = int(agent.agentium_id[0])  # 0,1,2,3
        task_type = task.task_type.value if task else "general"
        
        # Check if idle mode - override everything
        from backend.services.token_optimizer import token_optimizer
        if token_optimizer.idle_mode_active:
            return self._get_best_local_model()
        
        # Get best model based on agent tier and task
        model = self.get_best_model(task_type, agent_tier)
        
        # Log the allocation
        self._log_model_assignment(agent.agentium_id, model, task_type)
        
        return model
    
    def _log_model_assignment(self, agentium_id: str, model: ModelConfig, task_type: str):
        """Log model assignment for audit trail."""
        # This would integrate with your audit logging system
        print(f"📊 Agent {agentium_id} assigned {model.model_name} for {task_type}")
        # In production, write to AuditLog table


# Global instance
api_manager = None  # Will be initialized with db session

def init_api_manager(db: Session):
    """Initialize the global APIManager."""
    global api_manager
    
    # Check if any configurations exist
    config_count = db.query(UserModelConfig).filter_by(is_active='Y').count()
    
    if config_count == 0:
        # Create a default local configuration
        default_config = UserModelConfig(
            user_id="sovereign",
            config_name="Default Local Model",
            provider="local",
            provider_name="Local",
            default_model="kimi-2.5",
            is_default=True,
            is_active='Y',
            status='active'
        )
        db.add(default_config)
        db.commit()
        db.refresh(default_config)
        logger.info("Created default model configuration")
    
    api_manager = APIManager(db)
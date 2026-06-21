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
from backend.models.entities.user_config import ProviderType, ConnectionStatus

if TYPE_CHECKING:
    from backend.models.entities.task import Task


logger = logging.getLogger(__name__)


class ModelCapability(Enum):
    """Model capabilities for task matching."""
    CODE = "code"
    ANALYSIS = "analysis"
    CREATIVE = "creative"
    SIMPLE = "simple"
    IDLE = "idle"


# Capability priority order (highest → lowest)
CAPABILITY_PRIORITY = [
    ModelCapability.CODE,
    ModelCapability.ANALYSIS,
    ModelCapability.CREATIVE,
    ModelCapability.SIMPLE,
    ModelCapability.IDLE,
]


@dataclass
class ModelConfig:
    """Configuration for a specific model."""
    provider: str
    model_name: str
    config_id: str
    cost_per_1k_tokens: float
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
        self._load_configs()

    def _load_configs(self):
        """Load model configurations from the database."""
        try:
            configs = (
                self.db.query(UserModelConfig)
                .filter_by(is_active=True)
                .all()
            )
            for config in configs:
                model = self._config_to_model(config)
                if model:
                    self.models[config.id] = model
            logger.info(f"Loaded {len(self.models)} model configuration(s)")
        except Exception as e:
            logger.error(f"Failed to load model configs: {e}")

    def _config_to_model(self, config: UserModelConfig) -> Optional[ModelConfig]:
        """Convert a DB config to a ModelConfig dataclass."""
        try:
            # Determine capability from provider
            capability_map = {
                ProviderType.OPENAI:            ModelCapability.ANALYSIS,
                ProviderType.ANTHROPIC:         ModelCapability.ANALYSIS,
                ProviderType.GEMINI:            ModelCapability.ANALYSIS,
                ProviderType.GROQ:              ModelCapability.CODE,
                ProviderType.MISTRAL:           ModelCapability.CODE,
                ProviderType.MOONSHOT:          ModelCapability.CODE,
                ProviderType.DEEPSEEK:          ModelCapability.CODE,
                ProviderType.LOCAL:             ModelCapability.SIMPLE,
                ProviderType.CUSTOM:            ModelCapability.SIMPLE,
                ProviderType.OPENAI_COMPATIBLE: ModelCapability.SIMPLE,
            }
            capability = capability_map.get(config.provider, ModelCapability.SIMPLE)

            from backend.services.model_provider import calculate_cost
            cost_per_1k = calculate_cost(config.default_model, config.provider, 1000, 0)

            return ModelConfig(
                provider=config.provider.value if hasattr(config.provider, 'value') else str(config.provider),
                model_name=config.default_model,
                config_id=config.id,
                cost_per_1k_tokens=cost_per_1k,
                max_context_length=config.max_tokens or 4000,
                rate_limit_per_minute=config.rate_limit or 60,
                capability=capability,
                is_available=config.is_key_healthy(),
            )
        except Exception as e:
            logger.warning(f"Could not convert config {config.id}: {e}")
            return None

    def get_best_model(self, task_type: str = "general") -> Optional[ModelConfig]:
        """Get the best available model for a given task type."""
        available = [m for m in self.models.values() if m.is_available]
        if not available:
            logger.warning("No available models found")
            return None
        # Simple priority: lowest load first
        return sorted(available, key=lambda m: m.current_load)[0]

    def get_model_for_agent(self, agent: Agent, task_type: str = "general") -> Optional[ModelConfig]:
        """Get appropriate model for a specific agent."""
        # Check if agent has a preferred config
        if agent.preferred_config_id and agent.preferred_config_id in self.models:
            preferred = self.models[agent.preferred_config_id]
            if preferred.is_available:
                return preferred

        return self.get_best_model(task_type)

    def mark_model_used(self, config_id: str):
        """Increment current load counter."""
        if config_id in self.models:
            self.models[config_id].current_load += 1

    def mark_model_free(self, config_id: str):
        """Decrement current load counter."""
        if config_id in self.models:
            self.models[config_id].current_load = max(0, self.models[config_id].current_load - 1)

    def _log_model_assignment(self, agentium_id: str, model: ModelConfig, task_type: str):
        """Log model assignment for audit trail."""
        logger.info(f"📊 Agent {agentium_id} assigned {model.model_name} for {task_type}")

    # ------------------------------------------------------------------
    # Methods required by ModelAllocationService
    # ------------------------------------------------------------------

    def single_api_mode(self) -> bool:
        """
        Returns True when only one API model is available.
        Used by ModelAllocationService to skip tier-aware selection.
        """
        available = [m for m in self.models.values() if m.is_available]
        return len(available) == 1

    def _get_best_available_model_by_capability(
        self, target_capability: ModelCapability
    ) -> ModelConfig:
        """
        Return the best available model matching target_capability.

        Fallback chain:
          1. Exact capability match (lowest load wins)
          2. Walk up CAPABILITY_PRIORITY toward CODE until a match is found
          3. Walk down toward IDLE until a match is found
          4. Any available model (last resort)

        Raises ValueError if no models are available at all.
        """
        available = [m for m in self.models.values() if m.is_available]
        if not available:
            raise ValueError("No available models in APIManager")

        def _best_of(candidates: List[ModelConfig]) -> Optional[ModelConfig]:
            if not candidates:
                return None
            return sorted(candidates, key=lambda m: m.current_load)[0]

        # 1. Exact match
        exact = [m for m in available if m.capability == target_capability]
        if exact:
            return _best_of(exact)

        # 2. Walk capability priority list outward from target
        target_idx = CAPABILITY_PRIORITY.index(target_capability)

        # Try higher capabilities first (better quality)
        for cap in CAPABILITY_PRIORITY[:target_idx][::-1]:
            candidates = [m for m in available if m.capability == cap]
            if candidates:
                logger.info(
                    f"No {target_capability.value} model available; "
                    f"falling back to {cap.value}"
                )
                return _best_of(candidates)

        # Try lower capabilities (cheaper)
        for cap in CAPABILITY_PRIORITY[target_idx + 1:]:
            candidates = [m for m in available if m.capability == cap]
            if candidates:
                logger.info(
                    f"No {target_capability.value} model available; "
                    f"degrading to {cap.value}"
                )
                return _best_of(candidates)

        # 3. Absolute fallback — any available model
        logger.warning("Capability match failed entirely; using any available model")
        return _best_of(available)

    def _get_best_local_model(self) -> ModelConfig:
        """
        Return the best available LOCAL / OPENAI_COMPATIBLE model.
        Falls back to cheapest available model if no local model exists.

        Raises ValueError if no models are available at all.
        """
        available = [m for m in self.models.values() if m.is_available]
        if not available:
            raise ValueError("No available models in APIManager")

        local_providers = {"local", "openai_compatible", "custom"}
        local_models = [
            m for m in available
            if m.provider.lower() in local_providers
        ]

        if local_models:
            # Lowest load among local models
            return sorted(local_models, key=lambda m: m.current_load)[0]

        # No local model — fall back to cheapest overall
        logger.warning(
            "_get_best_local_model: no LOCAL provider found; "
            "returning cheapest available model"
        )
        return sorted(available, key=lambda m: m.cost_per_1k_tokens)[0]


# ---------------------------------------------------------------------------
# Global instance — initialised once at startup via init_api_manager()
# ---------------------------------------------------------------------------
api_manager: Optional[APIManager] = None


def init_api_manager(db: Session) -> APIManager:
    """
    Initialise the global APIManager.

    ``db`` MUST be a SQLAlchemy Session instance.  The function is deliberately
    defensive: if the wrong type is passed (e.g. a list of agents, a generator,
    a single ORM object) it will open its own session rather than crash, so
    startup continues even if a call-site bug exists elsewhere.
    """
    global api_manager

    # ── Type guard ────────────────────────────────────────────────────────────
    if not isinstance(db, Session):
        logger.error(
            f"init_api_manager received {type(db).__name__} instead of a "
            f"SQLAlchemy Session — this is a bug in the call site. "
            f"Opening a fresh session as fallback."
        )
        try:
            from backend.models.database import get_db as _get_db
            db = next(_get_db())
        except Exception as fallback_err:
            logger.error(f"Fallback session creation failed: {fallback_err}")
            raise TypeError(
                f"init_api_manager requires a SQLAlchemy Session, "
                f"got {type(db).__name__} and fallback also failed."
            ) from fallback_err

    try:
        config_count = db.query(UserModelConfig).filter_by(is_active=True).count()

        if config_count == 0:
            logger.info("No model configs found — creating default LOCAL config")
            default_config = UserModelConfig(
                user_id=None,
                config_name="Default Local Model",
                provider=ProviderType.LOCAL,
                provider_name="Local",
                default_model="kimi-2.5",
                is_default=True,
                is_active=True,
                status=ConnectionStatus.ACTIVE,
                rate_limit=60,
            )
            db.add(default_config)
            db.commit()
            db.refresh(default_config)
            logger.info("Created default model configuration")

        api_manager = APIManager(db)

        if len(api_manager.models) == 0:
            logger.warning("APIManager initialised with 0 models — check DB configs")

        logger.info(f"✅ APIManager initialised with {len(api_manager.models)} model(s)")
        return api_manager

    except Exception as e:
        logger.error(f"Failed to initialize APIManager: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise
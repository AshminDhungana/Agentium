"""
API routes for model configuration.
Supports ANY provider (OpenAI, Anthropic, Groq, Mistral, Gemini, Copilot, Local, etc.)

"""

import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from pydantic import BaseModel, SecretStr, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.models.database import get_db
from backend.models.entities.user_config import (
    UserModelConfig,
    ProviderType,
    ConnectionStatus,
    ModelUsageLog,
)
from backend.services.model_provider import ModelService
from backend.services.pricing_sync_service import PricingSyncService
from backend.models.entities.model_pricing import ModelPricing

from backend.api.schemas.examples import ErrorResponseExample, SuccessResponseExample, build_responses
from backend.core.config import settings
from backend.core.security import encrypt_api_key, decrypt_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/models", tags=["Model Configuration"])


_VALID_EFFORTS = {"none", "low", "medium", "high", "xhigh"}


def _validate_effort(v: str) -> str:
    if v not in _VALID_EFFORTS:
        raise ValueError("effort must be one of: none, low, medium, high, xhigh")
    return v


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pydantic Schemas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ModelConfigCreate(BaseModel):
    provider: ProviderType
    provider_name: Optional[str] = None
    config_name: str = Field(..., min_length=1, max_length=100)
    api_key: Optional[SecretStr] = None
    api_base_url: Optional[str] = None
    local_server_url: Optional[str] = None
    default_model: str = Field(..., min_length=1)
    available_models: List[str] = Field(default_factory=list)
    is_default: bool = False
    max_tokens: int = Field(default=4000, ge=100, le=128000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=1.0, ge=0.0, le=1.0)
    timeout_seconds: int = Field(default=60, ge=5, le=300)
    effort: str = Field(default="none")
    requests_per_minute: int = Field(default=60, ge=1, le=1000000,
                                            description="Max outbound requests/minute (whole integer)")
    tokens_per_minute: Optional[int] = Field(default=None, ge=1,
                                          description="Optional token budget per minute")
    max_concurrent_requests: Optional[int] = Field(default=10, ge=1,
                                              description="Max concurrent outbound requests for this key")

    @field_validator('provider', mode='before')
    @classmethod
    def _normalize_provider(cls, v):
        # Frontend sends lowercase provider ids (e.g. 'custom'); the ProviderType
        # enum is uppercase. Normalize so the request validates instead of 422.
        if isinstance(v, str):
            return v.upper()
        return v

    @field_validator('api_base_url', 'local_server_url')
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v

    @field_validator('effort')
    @classmethod
    def _check_effort(cls, v):
        return _validate_effort(v)


class ModelConfigUpdate(BaseModel):
    config_name: Optional[str] = None
    api_key: Optional[SecretStr] = None
    api_base_url: Optional[str] = None
    local_server_url: Optional[str] = None
    default_model: Optional[str] = None
    available_models: Optional[List[str]] = None
    is_default: Optional[bool] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    status: Optional[str] = None
    requests_per_minute: Optional[int] = Field(default=None, ge=1, le=1000000)
    tokens_per_minute: Optional[int] = Field(default=None, ge=1)
    max_concurrent_requests: Optional[int] = Field(default=None, ge=1)
    effort: Optional[str] = None

    @field_validator('effort')
    @classmethod
    def _check_effort(cls, v):
        return _validate_effort(v) if v is not None else v


class ModelConfigResponse(BaseModel):
    id: str
    provider: str
    provider_name: Optional[str] = None
    config_name: str
    default_model: str
    api_base_url: Optional[str] = None
    available_models: List[str] = Field(default_factory=list)
    status: str
    is_default: bool
    # api_key_masked was missing from original — frontend ModelConfig type expects it
    api_key_masked: Optional[str] = None
    requests_per_minute: int
    tokens_per_minute: Optional[int] = None
    max_concurrent_requests: Optional[int] = None
    settings: Dict[str, Any] = Field(default_factory=dict)
    effort: str = "none"
    last_tested: Optional[str] = None
    total_usage: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class ProviderInfo(BaseModel):
    id: str
    name: str
    display_name: str
    requires_api_key: bool
    requires_base_url: bool
    default_base_url: Optional[str] = None
    description: str
    popular_models: List[str] = Field(default_factory=list)


class TestResult(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[int] = None
    model: Optional[str] = None
    tokens: Optional[int] = None
    error: Optional[str] = None


class UniversalProviderCreate(BaseModel):
    provider_name: str
    api_base_url: str
    api_key: Optional[SecretStr] = None
    default_model: str
    config_name: Optional[str] = None
    is_default: bool = False


class FetchModelsRequest(BaseModel):
    provider: ProviderType
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    local_server_url: Optional[str] = None

    @field_validator('provider', mode='before')
    @classmethod
    def _normalize_provider(cls, v):
        # Frontend sends lowercase provider ids (e.g. 'openai', 'custom'); the
        # ProviderType enum is uppercase. Normalize so the request validates
        # instead of returning 422 (which previously crashed the React tree).
        if isinstance(v, str):
            return v.upper()
        return v


class ModelPrice(BaseModel):
    """Per-model price in USD per 1M tokens. ``None`` => free / unknown."""
    input_rate_per_1m: float
    output_rate_per_1m: float


class FetchModelsResponse(BaseModel):
    provider: str
    models: List[str]
    count: int
    default_recommended: Optional[str] = None
    # model_id (lower-cased) -> price, or None when the provider exposes
    # no pricing for that model (free / unknown — suppress in the UI).
    pricing: Dict[str, Optional[ModelPrice]] = Field(default_factory=dict)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Serialisation helper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _pricing_map_to_response(
    pricing_map: Dict[str, Optional[tuple]]
) -> Dict[str, Optional[ModelPrice]]:
    """
    Convert ModelService.fetch_model_pricing output (model_id ->
    (input_per_1m, output_per_1m) tuple, or None) into the JSON-safe
    response shape (model_id -> ModelPrice, or None for free/unknown).
    """
    return {
        mid: (ModelPrice(input_rate_per_1m=r[0], output_rate_per_1m=r[1])
                if r is not None else None)
        for mid, r in pricing_map.items()
    }


def _upsert_pricing(db: Session, provider_value: str,
                     pricing_map: Dict[str, Optional[tuple]]) -> None:
    """
    Persist non-free (paid) fetched prices into the model_pricings table so
    the existing PricingSyncService / calculate_cost pipeline stays in sync.
    Free / unknown models (None) are intentionally NOT written.
    """
    try:
        existing = {p.model_id: p for p in db.query(ModelPricing).all()}
        for mid, rates in pricing_map.items():
            if rates is None:
                continue
            inp, outp = rates
            if mid in existing:
                rec = existing[mid]
                if rec.input_rate_per_1m != inp or rec.output_rate_per_1m != outp:
                    rec.input_rate_per_1m = inp
                    rec.output_rate_per_1m = outp
                    rec.provider = provider_value
                    rec.is_active = True
            else:
                db.add(ModelPricing(
                    model_id=mid,
                    provider=provider_value,
                    input_rate_per_1m=inp,
                    output_rate_per_1m=outp,
                    is_active=True,
                ))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to upsert fetched pricing: {exc}")


def _serialize_config(config: UserModelConfig) -> Dict[str, Any]:
    """
    Serialize a UserModelConfig ORM object to a response dict.

    Kept as an explicit helper rather than relying purely on Pydantic
    from_attributes because SQLAlchemy Enum columns may return either
    a Python Enum member or a plain string depending on the engine
    dialect and session state. Explicit .value extraction is safer.
    """
    return {
        'id':             str(config.id),
        'provider':       config.provider.value if hasattr(config.provider, 'value') else str(config.provider),
        'provider_name':  config.provider_name,
        'config_name':    config.config_name,
        'default_model':  config.default_model,
        'api_base_url':   config.api_base_url,
        'available_models': config.available_models or [],
        'status':         config.status.value if hasattr(config.status, 'value') else str(config.status),
        'is_default':     config.is_default,
        # Previously missing — frontend expects this field to show masked key on cards
        'api_key_masked': config.api_key_masked,
        'requests_per_minute': config.requests_per_minute,
        'tokens_per_minute': config.tokens_per_minute,
        'max_concurrent_requests': config.max_concurrent_requests,
        'effort':        config.effort or 'none',
        'settings': {
            'max_tokens':  config.max_tokens,
            'temperature': config.temperature,
            'top_p':       config.top_p,
            'timeout':     config.timeout_seconds,
            'effort':      config.effort or 'none',
        },
        'last_tested': (
            config.last_tested_at.isoformat()
            if getattr(config, 'last_tested_at', None)
            else None
        ),
        'total_usage': {
            'requests': config.total_requests or 0,
            'tokens':   config.total_tokens   or 0,
            'cost_usd': round(config.estimated_cost_usd or 0, 4),
        },
    }


def _update_head_preferred_config_if_default(db: Session, config: UserModelConfig):
    """If the config is set as default, update Head of Council's preferred_config_id."""
    if config.is_default:
        try:
            from backend.models.entities.agents import HeadOfCouncil
            head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
            if head:
                head.preferred_config_id = str(config.id)
                db.commit()
                logger.info(
                    f"✅ Assigned default model config '{config.config_name}' ({config.id}) to Head 00001"
                )
        except Exception as e:
            logger.warning(f"⚠️ Failed to update Head preferred model config: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Routes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/providers",
    response_model=List[ProviderInfo],
    summary="List Providers",
    description="List ALL available provider types. Model lists fetched dynamically.",
    responses=build_responses(None),
)
async def list_providers():
    """List ALL available provider types. Model lists fetched dynamically."""
    providers = [
        ProviderInfo(
            id=ProviderType.OPENAI.value,
            name="openai",
            display_name="OpenAI",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.openai.com/v1",
            description="GPT-5.6, GPT-5.1, o4-mini and other OpenAI models",
            popular_models=["gpt-5.6", "gpt-5.6-mini", "gpt-5.1", "o4-mini"]
        ),
        ProviderInfo(
            id=ProviderType.ANTHROPIC.value,
            name="anthropic",
            display_name="Anthropic Claude",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.anthropic.com/v1",
            description="Claude Opus, Sonnet, Haiku - excellent reasoning and coding",
            popular_models=["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"]
        ),
        ProviderInfo(
            id=ProviderType.GEMINI.value,
            name="gemini",
            display_name="Google Gemini",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            description="Google's multimodal models (Gemini 2.5 Flash, 2.5 Pro)",
            popular_models=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]
        ),
        ProviderInfo(
            id=ProviderType.GROQ.value,
            name="groq",
            display_name="Groq",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.groq.com/openai/v1",
            description="Ultra-fast inference (100+ tokens/sec) with Llama 3.3",
            popular_models=["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "deepseek-r1-distill-llama-70b"]
        ),
        ProviderInfo(
            id=ProviderType.MISTRAL.value,
            name="mistral",
            display_name="Mistral AI",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.mistral.ai/v1",
            description="European AI with Mistral, Mixtral, and Codestral",
            popular_models=["mistral-large-latest", "mistral-small-latest", "codestral-latest"]
        ),
        ProviderInfo(
            id=ProviderType.TOGETHER.value,
            name="together",
            display_name="Together AI",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.together.xyz/v1",
            description="Access to 100+ open-source models (Llama 3.3, Qwen 2.5)",
            popular_models=["meta-llama/Llama-3.3-70B-Instruct-Turbo", "Qwen/Qwen2.5-72B-Instruct-Turbo", "deepseek-ai/DeepSeek-R1"]
        ),
        ProviderInfo(
            id=ProviderType.COHERE.value,
            name="cohere",
            display_name="Cohere",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.cohere.ai/v1",
            description="Command R+ and Embed models",
            popular_models=["command-r-plus", "command-r"]
        ),
        ProviderInfo(
            id=ProviderType.MOONSHOT.value,
            name="moonshot",
            display_name="Moonshot (Kimi)",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.moonshot.cn/v1",
            description="Kimi - Long context (200K+ tokens), Chinese/English",
            popular_models=["kimi-k2", "moonshot-v1-32k", "moonshot-v1-128k"]
        ),
        ProviderInfo(
            id=ProviderType.DEEPSEEK.value,
            name="deepseek",
            display_name="DeepSeek",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.deepseek.com/v1",
            description="DeepSeek Chat and Reasoner models",
            popular_models=["deepseek-chat", "deepseek-reasoner"]
        ),
        ProviderInfo(
            id=ProviderType.AZURE_OPENAI.value,
            name="azure_openai",
            display_name="Azure OpenAI",
            requires_api_key=True,
            requires_base_url=True,
            default_base_url="https://{resource}.openai.azure.com",
            description="Enterprise OpenAI through Azure (requires Endpoint URL)",
            popular_models=["gpt-5.6", "gpt-5.1", "gpt-4o"]
        ),
        ProviderInfo(
            id=ProviderType.LOCAL.value,
            name="local",
            display_name="Local (Ollama/LM Studio)",
            requires_api_key=False,
            requires_base_url=False,
            default_base_url=settings.OLLAMA_BASE_URL,
            description="Run models locally with Ollama or LM Studio",
            popular_models=["llama3.1", "mistral", "gemma2", "qwen2"]
        ),
    ]
    return providers


@router.post(
    "/configs",
    response_model=ModelConfigResponse,
    summary="Create Config",
    description="Create a new model configuration.",
    responses=build_responses(None),
)
async def create_config(
    config: ModelConfigCreate,
    db: Session = Depends(get_db),
    user_id: str = "sovereign",
):
    """Create a new model configuration."""
    if config.is_default:
        db.query(UserModelConfig).filter_by(user_id=user_id, is_default=True).update({"is_default": False})

    api_key_encrypted = None
    api_key_masked    = None
    if config.api_key:
        raw_key = config.api_key.get_secret_value()
        if raw_key:
            api_key_encrypted = encrypt_api_key(raw_key)
            api_key_masked    = f"...{raw_key[-4:]}"

    db_config = UserModelConfig(
        user_id           = user_id,
        provider          = config.provider,
        provider_name     = config.provider_name,
        config_name       = config.config_name,
        api_key_encrypted = api_key_encrypted,
        api_key_masked    = api_key_masked,
        api_base_url      = config.api_base_url,
        local_server_url  = config.local_server_url,
        default_model     = config.default_model,
        available_models  = config.available_models,
        is_default        = config.is_default,
        max_tokens        = config.max_tokens,
        temperature       = config.temperature,
        top_p             = config.top_p,
        timeout_seconds   = config.timeout_seconds,
        effort            = config.effort,
        requests_per_minute = config.requests_per_minute,
        tokens_per_minute   = config.tokens_per_minute,
        max_concurrent_requests = config.max_concurrent_requests,
        status            = ConnectionStatus.ACTIVE,
    )

    db.add(db_config)
    db.commit()
    db.refresh(db_config)

    _update_head_preferred_config_if_default(db, db_config)

    serialized = _serialize_config(db_config)
    try:
        from backend.services.config_versioning import ConfigVersioningService
        ConfigVersioningService.commit_snapshot("model_config", serialized["id"], user_id, serialized)
    except Exception as e:
        logger.error(f"Config versioning failed: {e}")

    # ── TRIGGER GENESIS IF SYSTEM NOT YET INITIALIZED ──────────────────────
    try:
        from backend.services.initialization_service import trigger_genesis_if_needed
        genesis_triggered = trigger_genesis_if_needed(db)
        logger.info(f"🚀 Genesis triggered from models.py: {genesis_triggered}")
    except Exception as e:
        logger.warning(f"Genesis auto-trigger failed (non-fatal): {e}")
    # ── END GENESIS TRIGGER ────────────────────────────────────────────────

    return serialized


@router.post(
    "/configs/universal",
    response_model=ModelConfigResponse,
    summary="Create Universal Config",
    description="Create configuration for ANY custom OpenAI-compatible provider.",
    responses=build_responses(None),
)
async def create_universal_config(
    input: UniversalProviderCreate,
    db: Session = Depends(get_db),
    user_id: str = "sovereign",
):
    """Create configuration for ANY custom OpenAI-compatible provider."""
    if input.is_default:
        db.query(UserModelConfig).filter_by(user_id=user_id, is_default=True).update({"is_default": False})

    api_key_encrypted = None
    api_key_masked    = None
    if input.api_key:
        raw_key = input.api_key.get_secret_value()
        if raw_key:
            api_key_encrypted = encrypt_api_key(raw_key)
            api_key_masked    = f"...{raw_key[-4:]}"

    config_name = input.config_name or f"{input.provider_name} Config"

    db_config = UserModelConfig(
        user_id           = user_id,
        provider          = ProviderType.CUSTOM,
        provider_name     = input.provider_name,
        config_name       = config_name,
        api_key_encrypted = api_key_encrypted,
        api_key_masked    = api_key_masked,
        api_base_url      = input.api_base_url,
        default_model     = input.default_model,
        is_default        = input.is_default,
        status            = ConnectionStatus.ACTIVE,
    )

    db.add(db_config)
    db.commit()
    db.refresh(db_config)

    _update_head_preferred_config_if_default(db, db_config)

    serialized = _serialize_config(db_config)
    try:
        from backend.services.config_versioning import ConfigVersioningService
        ConfigVersioningService.commit_snapshot("model_config", serialized["id"], user_id, serialized)
    except Exception as e:
        logger.error(f"Config versioning failed: {e}")

    # ── TRIGGER GENESIS IF SYSTEM NOT YET INITIALIZED ──────────────────────
    try:
        from backend.services.initialization_service import trigger_genesis_if_needed
        genesis_triggered = trigger_genesis_if_needed(db)
        logger.info(f"🚀 Genesis triggered from models.py: {genesis_triggered}")
    except Exception as e:
        logger.warning(f"Genesis auto-trigger failed (non-fatal): {e}")
    # ── END GENESIS TRIGGER ────────────────────────────────────────────────

    return serialized


@router.get(
    "/configs",
    response_model=List[ModelConfigResponse],
    summary="List Configs",
    description="List user's model configurations.",
    responses=build_responses(None),
)
async def list_configs(
    db: Session = Depends(get_db),
    user_id: str = "sovereign",
):
    """List user's model configurations."""
    configs = db.query(UserModelConfig).filter_by(user_id=user_id).all()
    return [_serialize_config(c) for c in configs]


@router.get(
    "/configs/{config_id}",
    response_model=ModelConfigResponse,
    summary="Get Config",
    description="Get specific configuration.",
    responses=build_responses(None),
)
async def get_config(
    config_id: str,
    db: Session = Depends(get_db),
    user_id: str = "sovereign",
):
    """Get specific configuration."""
    config = db.query(UserModelConfig).filter_by(id=config_id, user_id=user_id).first()
    if not config:
        raise NotFoundError(error="Configuration not found", code="CONFIGURATION_NOT_FOUND")

    return _serialize_config(config)


@router.put(
    "/configs/{config_id}",
    response_model=ModelConfigResponse,
    summary="Update Config",
    description="Update configuration.",
    responses=build_responses(None),
)
async def update_config(
    config_id: str,
    updates: ModelConfigUpdate,
    db: Session = Depends(get_db),
    user_id: str = "sovereign",
):
    """Update configuration."""
    config = db.query(UserModelConfig).filter_by(id=config_id, user_id=user_id).first()
    if not config:
        raise NotFoundError(error="Configuration not found", code="CONFIGURATION_NOT_FOUND")

    if updates.is_default and not config.is_default:
        db.query(UserModelConfig).filter_by(user_id=user_id, is_default=True).update({"is_default": False})

    update_data = updates.model_dump(exclude_unset=True)

    if "api_key" in update_data and update_data["api_key"]:
        raw_key = update_data["api_key"].get_secret_value()
        if raw_key:
            config.api_key_encrypted = encrypt_api_key(raw_key)
            config.api_key_masked    = f"...{raw_key[-4:]}"
        del update_data["api_key"]

    for field, value in update_data.items():
        if field in ('api_base_url', 'local_server_url') and value:
            if not value.startswith(('http://', 'https://')):
                raise BadRequestError(error=f"Invalid URL: {value}", code="INVALID_URL")
        setattr(config, field, value)

    if "api_key_encrypted" in update_data:
        config.status = ConnectionStatus.TESTING

    if updates.effort is not None:
        config.effort = _validate_effort(updates.effort)
        flag_modified(config, "effort")

    db.commit()
    db.refresh(config)

    _update_head_preferred_config_if_default(db, config)

    serialized = _serialize_config(config)
    try:
        from backend.services.config_versioning import ConfigVersioningService
        ConfigVersioningService.commit_snapshot("model_config", serialized["id"], user_id, serialized)
    except Exception as e:
        logger.error(f"Config versioning failed: {e}")

    return serialized


@router.delete(
    "/configs/{config_id}",
    summary="Delete Config",
    description="Delete configuration.",
    responses=build_responses(None),
)
async def delete_config(
    config_id: str,
    db: Session = Depends(get_db),
    user_id: str = "sovereign",
):
    """Delete configuration."""
    config = db.query(UserModelConfig).filter_by(id=config_id, user_id=user_id).first()
    if not config:
        raise NotFoundError(error="Configuration not found", code="CONFIGURATION_NOT_FOUND")

    remaining = db.query(UserModelConfig).filter_by(user_id=user_id).count()
    if remaining <= 1:
        raise BadRequestError(error="Cannot delete the only configuration", code="CANNOT_DELETE_THE_ONLY_CONFIGURATION")

    # If the config is referenced by Head of Council, we must clear/reassign it first to avoid FK constraint issues
    try:
        from backend.models.entities.agents import HeadOfCouncil
        head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        if head and head.preferred_config_id == config_id:
            head.preferred_config_id = None
            db.commit()
    except Exception as e:
        logger.warning(f"Failed to clear Head preferred model config reference: {e}")

    # ModelUsageLog.config_id is a non-nullable FK to user_model_configs with no
    # ON DELETE CASCADE. A config that has ever been used (e.g. a temp config
    # created during "Test Connection", which logs usage) would otherwise make
    # Postgres reject the delete with an IntegrityError → HTTP 500. Remove the
    # child rows explicitly before deleting the parent so the config can be
    # removed cleanly (this was the root cause of the silent 500 on Test
    # Connection and of the Delete button failing for any used config).
    try:
        db.query(ModelUsageLog).filter_by(config_id=config_id).delete()
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to purge usage logs for config {config_id}: {e}")
        db.rollback()

    is_deleted_default = config.is_default

    db.delete(config)
    db.commit()

    if is_deleted_default:
        # Find another active config to mark as default
        new_default = db.query(UserModelConfig).filter_by(
            user_id=user_id,
            status=ConnectionStatus.ACTIVE
        ).first() or db.query(UserModelConfig).filter_by(
            user_id=user_id
        ).first()

        if new_default:
            new_default.is_default = True
            db.commit()
            _update_head_preferred_config_if_default(db, new_default)

    return {"message": "Configuration deleted"}


@router.post(
    "/configs/{config_id}/test",
    response_model=TestResult,
    summary="Test Config",
    description="Test specific configuration.",
    responses=build_responses(None),
)
async def test_config(
    config_id: str,
    db: Session = Depends(get_db),
    user_id: str = "sovereign",
):
    """Test specific configuration."""
    config = db.query(UserModelConfig).filter_by(id=config_id, user_id=user_id).first()
    if not config:
        raise NotFoundError(error="Configuration not found", code="CONFIGURATION_NOT_FOUND")

    result = await ModelService.test_connection(config)
    return TestResult(
        success    = result["success"],
        message    = "Connection successful" if result["success"] else "Connection failed",
        latency_ms = result.get("latency_ms"),
        model      = result.get("model"),
        tokens     = result.get("tokens"),
        error      = result.get("error"),
    )


@router.get(
    "/configs/{config_id}/pricing",
    summary="Get Config Model Pricing",
    description="Return the live/registry price for a configuration's default model. "
                "Null when the model is free / has no pricing data (UI should suppress).",
    responses=build_responses(None),
)
async def get_config_pricing(
    config_id: str,
    db: Session = Depends(get_db),
    user_id: str = "sovereign",
):
    """Price for this config's default model (or null if free/unknown)."""
    config = db.query(UserModelConfig).filter_by(id=config_id, user_id=user_id).first()
    if not config:
        raise NotFoundError(error="Configuration not found", code="CONFIGURATION_NOT_FOUND")

    model_id = (config.default_model or "").lower().strip()
    rates = PricingSyncService.get_price(model_id, db) if model_id else None

    if rates is None:
        return {"model_id": model_id, "pricing": None}

    return {
        "model_id": model_id,
        "pricing": {
            "input_rate_per_1m": rates[0],
            "output_rate_per_1m": rates[1],
        },
    }


@router.post(
    "/configs/{config_id}/fetch-models",
    summary="Fetch Models",
    description="Dynamically fetch available models from provider API.",
    responses=build_responses(None),
)
async def fetch_models(
    config_id: str,
    db: Session = Depends(get_db),
    user_id: str = "sovereign",
):
    """Dynamically fetch available models from provider API."""
    config = db.query(UserModelConfig).filter_by(id=config_id, user_id=user_id).first()
    if not config:
        raise NotFoundError(error="Configuration not found", code="CONFIGURATION_NOT_FOUND")

    api_key: Optional[str] = None
    if config.api_key_encrypted:
        api_key = decrypt_api_key(config.api_key_encrypted)

    try:
        models = await ModelService.list_models_for_provider(
            config.provider,
            api_key,
            config.get_effective_base_url(),
        )
    except Exception as exc:
        logger.error("fetch_models failed for config %s: %s", config_id, exc, exc_info=True)
        raise InternalServerError(error=f"Failed to fetch models: {exc}", code="FAILED_TO_FETCH_MODELS") from exc

    config.available_models = models
    flag_modified(config, "available_models")  # Required: SQLAlchemy won't detect JSON column reassignment
    db.commit()

    # ── Live, provider-sourced pricing (free models suppressed) ──
    provider_value = config.provider.value if hasattr(config.provider, 'value') else str(config.provider)
    pricing_map = await ModelService.fetch_model_pricing(
        config.provider,
        api_key,
        config.get_effective_base_url(),
    )
    _upsert_pricing(db, provider_value, pricing_map)

    return {
        "provider": config.provider.value,
        "base_url": config.get_effective_base_url(),
        "models":   models,
        "count":    len(models),
        "pricing":  _pricing_map_to_response(pricing_map),
    }


@router.post(
    "/providers/fetch-models-direct",
    response_model=FetchModelsResponse,
    summary="Fetch Provider Models Direct",
    description="Fetch available models from a provider WITHOUT requiring an existing config. Used during the configuration setup wizard.",
    responses=build_responses(None),
)
async def fetch_provider_models_direct(
    request: FetchModelsRequest,
    db: Session = Depends(get_db),
):
    """
    Fetch available models from a provider WITHOUT requiring an existing config.
    Used during the configuration setup wizard.
    """
    try:
        models = await ModelService.list_models_for_provider(
            provider = request.provider,
            api_key  = request.api_key,
            base_url = request.api_base_url or request.local_server_url,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "fetch_provider_models_direct failed for provider %s: %s",
            request.provider,
            exc,
            exc_info=True,
        )
        raise InternalServerError(error=f"Failed to fetch models from {request.provider.value}: {exc}", code="FAILED_TO_FETCH_MODELS_FROM") from exc

    if not models:
        raise NotFoundError(error=f"No models found for provider {request.provider.value}", code="NO_MODELS_FOUND_FOR_PROVIDER")

    provider_value = request.provider.value
    pricing_map = await ModelService.fetch_model_pricing(
        request.provider,
        request.api_key,
        request.api_base_url or request.local_server_url,
    )
    _upsert_pricing(db, provider_value, pricing_map)

    return FetchModelsResponse(
        provider             = provider_value,
        models               = models,
        count                = len(models),
        default_recommended  = models[0] if models else None,
        pricing              = _pricing_map_to_response(pricing_map),
    )


@router.post(
    "/configs/{config_id}/set-default",
    summary="Set Default",
    description="Set a configuration as the default.",
    responses=build_responses(None),
)
async def set_default(
    config_id: str,
    db: Session = Depends(get_db),
    user_id: str = "sovereign",
):
    """Set a configuration as the default."""
    config = db.query(UserModelConfig).filter_by(id=config_id, user_id=user_id).first()
    if not config:
        raise NotFoundError(error="Configuration not found", code="CONFIGURATION_NOT_FOUND")

    db.query(UserModelConfig).filter_by(user_id=user_id, is_default=True).update({"is_default": False})
    config.is_default = True
    db.commit()

    _update_head_preferred_config_if_default(db, config)

    return {"message": "Configuration set as default", "config_id": config_id}


@router.get(
    "/configs/{config_id}/usage",
    summary="Get Usage",
    description="Get usage statistics for a configuration.",
    responses=build_responses(None),
)
async def get_usage(
    config_id: str,
    days: int = 7,
    db: Session = Depends(get_db),
    user_id: str = "sovereign",
):
    """Get usage statistics for a configuration."""
    config = db.query(UserModelConfig).filter_by(id=config_id, user_id=user_id).first()
    if not config:
        raise NotFoundError(error="Configuration not found", code="CONFIGURATION_NOT_FOUND")

    from datetime import datetime, timedelta

    since = datetime.utcnow() - timedelta(days=days)
    logs  = db.query(ModelUsageLog).filter(
        ModelUsageLog.config_id  == config_id,
        ModelUsageLog.created_at >= since,
    ).all()

    total_tokens = sum(log.total_tokens for log in logs)
    total_cost   = sum(float(log.cost_usd or 0) for log in logs)

    daily: Dict[str, Dict[str, Any]] = {}
    for log in logs:
        day = log.created_at.strftime("%Y-%m-%d")
        if day not in daily:
            daily[day] = {"tokens": 0, "requests": 0, "cost": 0.0}
        daily[day]["tokens"]   += log.total_tokens
        daily[day]["requests"] += 1
        daily[day]["cost"]     += float(log.cost_usd or 0)

    return {
        "period_days":      days,
        "total_tokens":     total_tokens,
        "total_requests":   len(logs),
        "total_cost_usd":   round(total_cost, 4),
        "success_rate":     sum(1 for log in logs if log.success) / max(len(logs), 1) * 100,
        "daily_breakdown":  daily,
        "by_model":         {},
    }
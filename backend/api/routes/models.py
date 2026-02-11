"""
API routes for model configuration.
Supports ANY provider (OpenAI, Anthropic, Groq, Mistral, Gemini, Copilot, Local, etc.)
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, SecretStr, Field, field_validator
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.models.entities.user_config import UserModelConfig, ProviderType, ConnectionStatus, ModelUsageLog
from backend.services.model_provider import ModelService
from backend.core.security import encrypt_api_key, decrypt_api_key

router = APIRouter(prefix="/models", tags=["Model Configuration"])


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
    
    @field_validator('api_base_url', 'local_server_url')
    @classmethod
    def validate_url(cls, v):
        if v and not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v


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
    settings: Dict[str, Any] = Field(default_factory=dict)
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


class FetchModelsResponse(BaseModel):
    provider: str
    models: List[str]
    count: int
    default_recommended: Optional[str] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Routes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/providers", response_model=List[ProviderInfo])
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
            description="GPT-4, GPT-3.5 Turbo, and other OpenAI models"
        ),
        ProviderInfo(
            id=ProviderType.ANTHROPIC.value,
            name="anthropic",
            display_name="Anthropic Claude",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.anthropic.com/v1",
            description="Claude 3 Opus, Sonnet, Haiku - excellent reasoning"
        ),
        ProviderInfo(
            id=ProviderType.GEMINI.value,
            name="gemini",
            display_name="Google Gemini",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            description="Google's multimodal models (Gemini 1.5 Pro, Flash, etc.)"
        ),
        ProviderInfo(
            id=ProviderType.GROQ.value,
            name="groq",
            display_name="Groq",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.groq.com/openai/v1",
            description="Ultra-fast inference (100+ tokens/sec) with Llama 3"
        ),
        ProviderInfo(
            id=ProviderType.MISTRAL.value,
            name="mistral",
            display_name="Mistral AI",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.mistral.ai/v1",
            description="European AI with Mistral and Mixtral models"
        ),
        ProviderInfo(
            id=ProviderType.TOGETHER.value,
            name="together",
            display_name="Together AI",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.together.xyz/v1",
            description="Access to 100+ open-source models"
        ),
        ProviderInfo(
            id=ProviderType.COHERE.value,
            name="cohere",
            display_name="Cohere",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.cohere.ai/v1",
            description="Command R+ and Embed models"
        ),
        ProviderInfo(
            id=ProviderType.MOONSHOT.value,
            name="moonshot",
            display_name="Moonshot (Kimi 2.5)",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.moonshot.cn/v1",
            description="Kimi 2.5 - Long context (200K+ tokens), Chinese/English"
        ),
        ProviderInfo(
            id=ProviderType.DEEPSEEK.value,
            name="deepseek",
            display_name="DeepSeek",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.deepseek.com/v1",
            description="DeepSeek Coder and Chat models"
        ),
        ProviderInfo(
            id=ProviderType.AZURE_OPENAI.value,
            name="azure_openai",
            display_name="Azure OpenAI",
            requires_api_key=True,
            requires_base_url=True,
            default_base_url=None,
            description="Enterprise OpenAI through Azure"
        ),
        ProviderInfo(
            id=ProviderType.LOCAL.value,
            name="local",
            display_name="Local (Ollama/LM Studio)",
            requires_api_key=False,
            requires_base_url=False,
            default_base_url="http://localhost:11434/v1",
            description="Run models locally with Ollama or LM Studio"
        ),
        ProviderInfo(
            id=ProviderType.CUSTOM.value,
            name="custom",
            display_name="Custom Provider",
            requires_api_key=True,
            requires_base_url=True,
            default_base_url=None,
            description="Any OpenAI-compatible API endpoint"
        ),
    ]
    return providers


@router.post("/configs", response_model=ModelConfigResponse)
async def create_config(
    config: ModelConfigCreate,
    db: Session = Depends(get_db),
    user_id: str = "sovereign"
):
    """Create a new model configuration."""
    
    # If setting as default, unset other defaults
    if config.is_default:
        db.query(UserModelConfig).filter_by(user_id=user_id, is_default=True).update({"is_default": False})
    
    # Encrypt API key if provided
    api_key_encrypted = None
    api_key_masked = None
    if config.api_key:
        raw_key = config.api_key.get_secret_value()
        if raw_key:
            api_key_encrypted = encrypt_api_key(raw_key)
            api_key_masked = f"...{raw_key[-4:]}"
    
    # Create config
    db_config = UserModelConfig(
        user_id=user_id,
        provider=config.provider,
        provider_name=config.provider_name,
        config_name=config.config_name,
        api_key_encrypted=api_key_encrypted,
        api_key_masked=api_key_masked,
        api_base_url=config.api_base_url,
        local_server_url=config.local_server_url,
        default_model=config.default_model,
        available_models=config.available_models,
        is_default=config.is_default,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        top_p=config.top_p,
        timeout_seconds=config.timeout_seconds,
        status=ConnectionStatus.ACTIVE
    )
    
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    
    return _serialize_config(db_config)


@router.post("/configs/universal", response_model=ModelConfigResponse)
async def create_universal_config(
    input: UniversalProviderCreate,
    db: Session = Depends(get_db),
    user_id: str = "sovereign"
):
    """Create configuration for ANY custom OpenAI-compatible provider."""
    
    if input.is_default:
        db.query(UserModelConfig).filter_by(user_id=user_id, is_default=True).update({"is_default": False})
    
    api_key_encrypted = None
    api_key_masked = None
    if input.api_key:
        raw_key = input.api_key.get_secret_value()
        if raw_key:
            api_key_encrypted = encrypt_api_key(raw_key)
            api_key_masked = f"...{raw_key[-4:]}"
    
    config_name = input.config_name or f"{input.provider_name} Config"
    
    db_config = UserModelConfig(
        user_id=user_id,
        provider=ProviderType.CUSTOM,
        provider_name=input.provider_name,
        config_name=config_name,
        api_key_encrypted=api_key_encrypted,
        api_key_masked=api_key_masked,
        api_base_url=input.api_base_url,
        default_model=input.default_model,
        is_default=input.is_default,
        status=ConnectionStatus.ACTIVE
    )
    
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    
    return _serialize_config(db_config)


def _serialize_config(config: UserModelConfig) -> Dict[str, Any]:
    """Serialize config to response format with safe defaults."""
    return {
        'id': str(config.id),
        'provider': config.provider.value if hasattr(config.provider, 'value') else str(config.provider),
        'provider_name': config.provider_name,
        'config_name': config.config_name,
        'default_model': config.default_model,
        'api_base_url': config.api_base_url,
        'available_models': config.available_models or [],
        'status': config.status.value if hasattr(config.status, 'value') else str(config.status),
        'is_default': config.is_default,
        'settings': {
            'max_tokens': config.max_tokens,
            'temperature': config.temperature,
            'top_p': config.top_p,
            'timeout': config.timeout_seconds
        },
        'last_tested': config.last_tested_at.isoformat() if hasattr(config, 'last_tested_at') and config.last_tested_at else None,
        'total_usage': {
            'requests': config.total_requests or 0,
            'tokens': config.total_tokens or 0,
            'cost_usd': round(config.estimated_cost_usd or 0, 4)
        }
    }


@router.get("/configs", response_model=List[ModelConfigResponse])
async def list_configs(
    db: Session = Depends(get_db),
    user_id: str = "sovereign"
):
    """List user's model configurations."""
    configs = db.query(UserModelConfig).filter_by(user_id=user_id).all()
    return [_serialize_config(c) for c in configs]


@router.get("/configs/{config_id}", response_model=ModelConfigResponse)
async def get_config(config_id: str, db: Session = Depends(get_db), user_id: str = "sovereign"):
    """Get specific configuration."""
    config = db.query(UserModelConfig).filter_by(id=config_id, user_id=user_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    return _serialize_config(config)


@router.put("/configs/{config_id}", response_model=ModelConfigResponse)
async def update_config(
    config_id: str,
    updates: ModelConfigUpdate,
    db: Session = Depends(get_db),
    user_id: str = "sovereign"
):
    """Update configuration."""
    config = db.query(UserModelConfig).filter_by(id=config_id, user_id=user_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    if updates.is_default and not config.is_default:
        db.query(UserModelConfig).filter_by(user_id=user_id, is_default=True).update({"is_default": False})
    
    update_data = updates.model_dump(exclude_unset=True)
    
    if "api_key" in update_data and update_data["api_key"]:
        raw_key = update_data["api_key"].get_secret_value()
        if raw_key:
            config.api_key_encrypted = encrypt_api_key(raw_key)
            config.api_key_masked = f"...{raw_key[-4:]}"
        del update_data["api_key"]
    
    for field, value in update_data.items():
        if field in ['api_base_url', 'local_server_url'] and value:
            if not value.startswith(('http://', 'https://')):
                raise HTTPException(status_code=400, detail=f"Invalid URL: {value}")
        setattr(config, field, value)
    
    if "api_key_encrypted" in update_data:
        config.status = ConnectionStatus.TESTING
    
    db.commit()
    db.refresh(config)
    
    return _serialize_config(config)


@router.delete("/configs/{config_id}")
async def delete_config(config_id: str, db: Session = Depends(get_db), user_id: str = "sovereign"):
    """Delete configuration."""
    config = db.query(UserModelConfig).filter_by(id=config_id, user_id=user_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    remaining = db.query(UserModelConfig).filter_by(user_id=user_id).count()
    if remaining <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the only configuration")
    
    db.delete(config)
    db.commit()
    return {"message": "Configuration deleted"}


@router.post("/configs/{config_id}/test", response_model=TestResult)
async def test_config(
    config_id: str,
    db: Session = Depends(get_db),
    user_id: str = "sovereign"
):
    """Test specific configuration."""
    config = db.query(UserModelConfig).filter_by(id=config_id, user_id=user_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    result = await ModelService.test_connection(config)
    return TestResult(
        success=result["success"],
        message="Connection successful" if result["success"] else "Connection failed",
        latency_ms=result.get("latency_ms"),
        model=result.get("model"),
        tokens=result.get("tokens"),
        error=result.get("error")
    )


@router.post("/configs/{config_id}/fetch-models")
async def fetch_models(
    config_id: str,
    db: Session = Depends(get_db),
    user_id: str = "sovereign"
):
    """Dynamically fetch available models from provider API."""
    config = db.query(UserModelConfig).filter_by(id=config_id, user_id=user_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    try:
        api_key = None
        if config.api_key_encrypted:
            api_key = decrypt_api_key(config.api_key_encrypted)
        
        models = await ModelService.list_models_for_provider(
            config.provider,
            api_key,
            config.get_effective_base_url()
        )
        
        config.available_models = models
        db.commit()
        
        return {
            "provider": config.provider.value,
            "base_url": config.get_effective_base_url(),
            "models": models,
            "count": len(models)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {str(e)}")


@router.post("/providers/fetch-models-direct", response_model=FetchModelsResponse)
async def fetch_provider_models_direct(request: FetchModelsRequest):
    """
    Fetch available models from provider WITHOUT requiring a config.
    This is used during the configuration setup flow.
    """
    try:
        models = await ModelService.list_models_for_provider(
            provider=request.provider,
            api_key=request.api_key,
            base_url=request.api_base_url or request.local_server_url
        )
        
        if not models:
            raise HTTPException(
                status_code=404,
                detail=f"No models found for provider {request.provider.value}"
            )
        
        return FetchModelsResponse(
            provider=request.provider.value,
            models=models,
            count=len(models),
            default_recommended=models[0] if models else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch models from {request.provider.value}: {str(e)}"
        )


@router.post("/configs/{config_id}/set-default")
async def set_default(config_id: str, db: Session = Depends(get_db), user_id: str = "sovereign"):
    """Set as default."""
    config = db.query(UserModelConfig).filter_by(id=config_id, user_id=user_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    db.query(UserModelConfig).filter_by(user_id=user_id, is_default=True).update({"is_default": False})
    config.is_default = True
    db.commit()
    
    return {"message": "Configuration set as default", "config_id": config_id}


@router.get("/configs/{config_id}/usage")
async def get_usage(
    config_id: str,
    days: int = 7,
    db: Session = Depends(get_db),
    user_id: str = "sovereign"
):
    """Get usage statistics."""
    config = db.query(UserModelConfig).filter_by(id=config_id, user_id=user_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    from datetime import datetime, timedelta
    
    since = datetime.utcnow() - timedelta(days=days)
    logs = db.query(ModelUsageLog).filter(
        ModelUsageLog.config_id == config_id,
        ModelUsageLog.created_at >= since
    ).all()
    
    total_tokens = sum(log.total_tokens for log in logs)
    total_cost = sum(float(log.cost_usd or 0) for log in logs)
    
    daily = {}
    for log in logs:
        day = log.created_at.strftime("%Y-%m-%d")
        if day not in daily:
            daily[day] = {"tokens": 0, "requests": 0, "cost": 0.0}
        daily[day]["tokens"] += log.total_tokens
        daily[day]["requests"] += 1
        daily[day]["cost"] += float(log.cost_usd or 0)
    
    return {
        "period_days": days,
        "total_tokens": total_tokens,
        "total_requests": len(logs),
        "total_cost_usd": round(total_cost, 4),
        "success_rate": sum(1 for log in logs if log.success) / max(len(logs), 1) * 100,
        "daily_breakdown": daily,
        "by_model": {}
    }
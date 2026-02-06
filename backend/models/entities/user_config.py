"""
User model configuration for Agentium.
Supports ANY API provider (OpenAI, Anthropic, Groq, Mistral, Gemini, local, etc.)
"""
import enum
import random
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Enum, JSON, Text, ForeignKey
from sqlalchemy.orm import validates
from sqlalchemy.orm import relationship
from backend.models.entities.base import BaseEntity


class ProviderType(str, enum.Enum):
    """
    Provider types - EXTENSIBLE for any API.
    Use CUSTOM for any OpenAI-compatible endpoint not listed.
    """
    # Major providers (pre-configured)
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"  # Google
    
    # Popular third-party (pre-configured)
    GROQ = "groq"
    MISTRAL = "mistral"
    COHERE = "cohere"
    TOGETHER = "together"
    FIREWORKS = "fireworks"
    PERPLEXITY = "perplexity"
    AI21 = "ai21"
    
    # Chinese/International providers (pre-configured)
    MOONSHOT = "moonshot"  # Kimi 2.5
    DEEPSEEK = "deepseek"
    QIANWEN = "qianwen"    # Alibaba
    ZHIPU = "zhipu"        # ChatGLM
    
    # Microsoft
    AZURE_OPENAI = "azure_openai"
    
    # Local/Custom (universal handler)
    LOCAL = "local"        # Ollama, llama.cpp, LM Studio
    CUSTOM = "custom"      # ANY OpenAI-compatible API not listed above
    
    # Special
    OPENAI_COMPATIBLE = "openai_compatible"  # Generic fallback


class ConnectionStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    TESTING = "testing"
    ERROR = "error"


class UserModelConfig(BaseEntity):
    """
    Universal model configuration.
    Supports ANY provider through flexible schema.
    """
    
    __tablename__ = 'user_model_configs'
    
    # User ownership (for multi-user support)
    user_id = Column(String(36), default="sovereign", nullable=False)
    
    # Provider identification
    provider = Column(Enum(ProviderType), nullable=False)
    provider_name = Column(String(50), nullable=True)  # Custom display name (e.g., "My Groq")
    
    # Configuration name (user-defined label)
    config_name = Column(String(100), nullable=False)
    
    # Authentication
    api_key_encrypted = Column(Text, nullable=True)  # Encrypted API key
    api_key_masked = Column(String(10), nullable=True)  # Last 4 chars for display (e.g., "...x83Ab")
    
    # Endpoint configuration (flexible for ANY provider)
    api_base_url = Column(String(500), nullable=True)  # e.g., https://api.groq.com/openai/v1
    
    # For Windows Copilot/Azure specific
    azure_endpoint = Column(String(500), nullable=True)
    azure_deployment = Column(String(100), nullable=True)
    
    # Model configuration
    default_model = Column(String(100), nullable=False)  # e.g., "llama3-70b-8192"
    available_models = Column(JSON, default=list)  # List of available models from this provider
    model_family = Column(String(50), nullable=True)  # e.g., "GPT", "Claude", "Llama"
    
    # Local server configuration (for LOCAL type)
    local_server_url = Column(String(500), nullable=True)  # e.g., http://localhost:11434/v1
    
    # Generation parameters
    max_tokens = Column(Integer, default=4000)
    temperature = Column(Float, default=0.7)
    top_p = Column(Float, default=1.0)
    timeout_seconds = Column(Integer, default=60)
    
    # Status tracking
    status = Column(Enum(ConnectionStatus), default=ConnectionStatus.TESTING)
    last_error = Column(Text, nullable=True)
    last_tested_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    
    # Usage tracking
    is_default = Column(Boolean, default=False)
    total_requests = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    
    # Cost tracking (in USD)
    estimated_cost_usd = Column(Float, default=0.0)
    
    # Metadata for extensibility
    extra_params = Column(JSON, default=dict)  # Provider-specific settings
    
    # Relationships
    usage_logs = relationship("ModelUsageLog", back_populates="config", lazy="dynamic")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.agentium_id:
            date_part = datetime.utcnow().strftime('%y%m%d')  # 6 chars: 260206
            random_part = f"{random.randint(0, 999):03d}"  # 3 chars
            self.agentium_id = f"C{date_part}{random_part}"  # 1+6+3 = 10 chars
    
    @validates('api_key_encrypted')
    def mask_api_key(self, key, value):
        """Store masked version for display."""
        if value and len(value) > 4:
            # In real implementation, decrypt first 4 after encryption? No, just mask the raw input
            pass  # Handled in service layer
        return value
    
    def get_effective_base_url(self) -> Optional[str]:
        """Get the effective API base URL."""
        if self.provider == ProviderType.LOCAL and self.local_server_url:
            return self.local_server_url
        if self.provider == ProviderType.OPENAI and not self.api_base_url:
            return "https://api.openai.com/v1"
        if self.provider == ProviderType.ANTHROPIC and not self.api_base_url:
            return "https://api.anthropic.com/v1"
        if self.provider == ProviderType.GROQ and not self.api_base_url:
            return "https://api.groq.com/openai/v1"
        if self.provider == ProviderType.MISTRAL and not self.api_base_url:
            return "https://api.mistral.ai/v1"
        if self.provider == ProviderType.TOGETHER and not self.api_base_url:
            return "https://api.together.xyz/v1"
        if self.provider == ProviderType.FIREWORKS and not self.api_base_url:
            return "https://api.fireworks.ai/inference/v1"
        if self.provider == ProviderType.MOONSHOT and not self.api_base_url:
            return "https://api.moonshot.cn/v1"
        if self.provider == ProviderType.DEEPSEEK and not self.api_base_url:
            return "https://api.deepseek.com/v1"
        return self.api_base_url
    
    def requires_api_key(self) -> bool:
        """Check if this provider requires an API key."""
        no_key_required = [ProviderType.LOCAL]
        return self.provider not in no_key_required
    
    def to_dict(self, include_api_key=False):
        """Convert to dictionary."""
        base = super().to_dict()
        base.update({
            'provider': self.provider.value,
            'provider_name': self.provider_name or self.provider.value,
            'config_name': self.config_name,
            'api_key_masked': self.api_key_masked,
            'api_base_url': self.get_effective_base_url(),
            'default_model': self.default_model,
            'available_models': self.available_models,
            'status': self.status.value,
            'is_default': self.is_default,
            'settings': {
                'max_tokens': self.max_tokens,
                'temperature': self.temperature,
                'top_p': self.top_p,
                'timeout': self.timeout_seconds
            }
        })
        
        if include_api_key and self.api_key_encrypted:
            from backend.core.security import decrypt_api_key
            try:
                base['api_key'] = decrypt_api_key(self.api_key_encrypted)
            except:
                base['api_key'] = None
                
        return base
    
    def increment_usage(self, tokens: int, cost_usd: float = 0.0):
        """Track usage."""
        self.total_requests += 1
        self.total_tokens += tokens
        self.estimated_cost_usd += cost_usd
        self.last_used_at = datetime.utcnow()
    
    def mark_tested(self, success: bool, error: str = None):
        """Update test status."""
        self.last_tested_at = datetime.utcnow()
        self.status = ConnectionStatus.ACTIVE if success else ConnectionStatus.ERROR
        if error:
            self.last_error = error[:500]  # Limit error length
    
    def mask_key_for_display(self, raw_key: str):
        """Store masked version."""
        if raw_key and len(raw_key) > 4:
            self.api_key_masked = f"...{raw_key[-4:]}"
        else:
            self.api_key_masked = None


class ModelUsageLog(BaseEntity):
    """Track API usage per configuration."""
    
    __tablename__ = 'model_usage_logs'
    
    config_id = Column(String(36), ForeignKey('user_model_configs.id'), nullable=False)
    
    provider = Column(Enum(ProviderType), nullable=False)
    model_used = Column(String(100), nullable=False)
    
    request_type = Column(String(50), default="chat")  # chat, completion, embedding
    total_tokens = Column(Integer, default=0)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    
    latency_ms = Column(Integer, nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    
    # Cost tracking
    cost_usd = Column(Float, nullable=True)
    
    # Metadata
    request_metadata = Column(JSON, default=dict)  # Agent ID, task info, etc.
    
    # Relationships
    config = relationship("UserModelConfig", back_populates="usage_logs")
"""
User model configuration for Agentium.
Supports ANY API provider (OpenAI, Anthropic, Groq, Mistral, Gemini, local, etc.)
"""
import enum
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Enum, JSON, Text, ForeignKey
from sqlalchemy.orm import validates
from sqlalchemy.orm import relationship
from backend.models.entities.base import BaseEntity
from backend.core.config import settings


class ProviderType(str, enum.Enum):
    """
    Provider types - EXTENSIBLE for any API.
    Use CUSTOM for any OpenAI-compatible endpoint not listed.
    """
    # Major providers (pre-configured)
    OPENAI = "OPENAI"
    ANTHROPIC = "ANTHROPIC"
    GEMINI = "GEMINI"  # Google

    # Popular third-party (pre-configured)
    GROQ = "GROQ"
    MISTRAL = "MISTRAL"
    COHERE = "COHERE"
    TOGETHER = "TOGETHER"
    FIREWORKS = "FIREWORKS"
    PERPLEXITY = "PERPLEXITY"
    AI21 = "AI21"

    # Chinese/International providers (pre-configured)
    MOONSHOT = "MOONSHOT"  # Kimi 2.5
    DEEPSEEK = "DEEPSEEK"
    QIANWEN = "QIANWEN"    # Alibaba
    ZHIPU = "ZHIPU"        # ChatGLM

    # Microsoft
    AZURE_OPENAI = "AZURE_OPENAI"

    # Local/Custom (universal handler)
    LOCAL = "LOCAL"        # Ollama, llama.cpp, LM Studio
    CUSTOM = "CUSTOM"      # ANY OpenAI-compatible API not listed above

    # Special
    OPENAI_COMPATIBLE = "OPENAI_COMPATIBLE"  # Generic fallback


class ConnectionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    TESTING = "TESTING"
    ERROR = "ERROR"


class UserModelConfig(BaseEntity):
    """
    Universal model configuration.
    Supports ANY provider through flexible schema.
    """

    __tablename__ = 'user_model_configs'

    # User ownership — nullable so system/sovereign configs work without a real user row.
    # No Python default here: passing user_id=None inserts NULL, which is valid.
    # Do NOT set default="sovereign" — that string is not a real users.id and will
    # trigger a FK violation. Use NULL for all system-level configs.
    user_id = Column(String(36), nullable=True)

    # Provider identification
    provider = Column(Enum(ProviderType), nullable=False)
    provider_name = Column(String(50), nullable=True)  # Custom display name

    # Configuration name (user-defined label)
    config_name = Column(String(100), nullable=False)

    # Authentication
    api_key_encrypted = Column(Text, nullable=True)
    api_key_masked = Column(String(10), nullable=True)

    # Endpoint configuration
    api_base_url = Column(String(500), nullable=True)

    # Azure-specific
    azure_endpoint = Column(String(500), nullable=True)
    azure_deployment = Column(String(100), nullable=True)

    # Model configuration
    default_model = Column(String(100), nullable=False)
    available_models = Column(JSON, default=list)
    model_family = Column(String(50), nullable=True)

    # Local server configuration
    local_server_url = Column(String(500), nullable=True)

    # Generation parameters
    max_tokens = Column(Integer, default=4000)
    temperature = Column(Float, default=0.7)
    top_p = Column(Float, default=1.0)
    timeout_seconds = Column(Integer, default=60)

    # Reasoning effort for extended-thinking providers
    effort = Column(String(16), default="none", nullable=False,
                  comment="Reasoning effort: none|low|medium|high|xhigh")

    # Status tracking
    status = Column(Enum(ConnectionStatus), default=ConnectionStatus.TESTING)
    last_error = Column(Text, nullable=True)
    last_tested_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)

    # Usage tracking
    is_default = Column(Boolean, default=False)
    total_requests = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    # requests_per_minute replaces the old `rate_limit` column (default 60).
    requests_per_minute = Column(Integer, default=60, nullable=False,
                                 comment="Max outbound requests/minute for this key (whole integer)")
    tokens_per_minute = Column(Integer, nullable=True,
                               comment="Optional token budget per minute")
    max_concurrent_requests = Column(Integer, default=10, nullable=False,
                                     comment="Max concurrent outbound requests for this key")

    # Cost tracking (in USD)
    estimated_cost_usd = Column(Float, default=0.0)

    # Metadata for extensibility
    extra_params = Column(JSON, default=dict)

    # Relationships
    usage_logs = relationship("ModelUsageLog", back_populates="config", lazy="dynamic")

    priority = Column(Integer, default=999, nullable=False,
                      comment="Priority order: 1=primary, 2=secondary, etc. Lower = higher priority")
    failure_count = Column(Integer, default=0, nullable=False,
                           comment="Consecutive failures since last success")
    last_failure_at = Column(DateTime, nullable=True,
                             comment="Timestamp of last failure")
    cooldown_until = Column(DateTime, nullable=True,
                            comment="Do not use this key until this timestamp")
    monthly_budget_usd = Column(Float, default=0.0, nullable=False,
                                comment="Maximum monthly spend for this key (0=unlimited)")
    current_spend_usd = Column(Float, default=0.0, nullable=False,
                               comment="Current month spend tracking")
    last_spend_reset = Column(DateTime, default=datetime.utcnow, nullable=False,
                              comment="When current_spend_usd was last reset")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.agentium_id:
            date_part = datetime.utcnow().strftime('%y%m%d')
            # Was random.randint(0, 999) — only 1,000 values shared by every
            # config created that day. With db_session function-scoped and
            # genesis re-run per test, a CI suite easily generates hundreds
            # of these on the same day; by the birthday paradox that pool
            # collides with high probability (e.g. ~78% chance of at least
            # one collision after just 50 draws from a 1,000-value space),
            # producing intermittent unique-constraint failures in unrelated
            # tests. uuid4()'s 8 hex chars give ~4.3 billion values instead.
            random_part = uuid.uuid4().hex[:8]
            self.agentium_id = f"C{date_part}{random_part}"

    def is_key_healthy(self) -> bool:
        """Check if key is available for use (not in cooldown, not exhausted)."""
        if self.cooldown_until and datetime.utcnow() < self.cooldown_until:
            return False
        if self.status == ConnectionStatus.ERROR:
            return False
        if self.monthly_budget_usd > 0 and self.current_spend_usd >= self.monthly_budget_usd:
            return False
        return True

    def record_failure(self):
        """Increment failure count and potentially trigger cooldown."""
        from datetime import timedelta
        self.failure_count += 1
        self.last_failure_at = datetime.utcnow()
        if self.failure_count >= 3:
            self.cooldown_until = datetime.utcnow() + timedelta(minutes=5)
            self.status = ConnectionStatus.ERROR

    def record_success(self):
        """Reset failure count on success."""
        self.failure_count = 0
        self.last_failure_at = None
        self.status = ConnectionStatus.ACTIVE
        self.cooldown_until = None

    def record_spend(self, cost_usd: float):
        """
        Add to current spend and check for monthly reset.

        ⚠️ CONCURRENCY WARNING: this mutates Python attributes on an
        in-memory ORM instance via simple read-modify-write
        (self.current_spend_usd += cost_usd). It is only safe to call this
        when you hold exclusive access to this row for the duration of the
        surrounding transaction (e.g. a single request handler that loaded,
        updates, and commits this object with no other writer in between).

        Under concurrent requests — e.g. multiple agents hitting the same
        key/config at once — two sessions can each load this row with
        current_spend_usd=10.0, each add their own delta in Python, and
        each commit; whichever commits last overwrites the other's
        increment, silently losing tracked spend and letting real spend
        exceed monthly_budget_usd without the ledger ever reflecting it.

        For any code path where multiple processes/requests might record
        spend against the same config concurrently, use
        APIKeyManager.record_spend() instead (backend.services.api_key_manager),
        which performs the increment as a single atomic SQL UPDATE and
        cannot lose a concurrent write. This method remains here for
        simple, single-writer contexts (tests, scripts, migrations) where
        the overhead of a manager call isn't warranted.
        """
        now = datetime.utcnow()
        if self.last_spend_reset.month != now.month or self.last_spend_reset.year != now.year:
            self.current_spend_usd = 0.0
            self.last_spend_reset = now
        self.current_spend_usd += cost_usd

    @validates('api_key_encrypted')
    def mask_api_key(self, key, value):
        """Store masked version for display."""
        return value

    # Default OpenAI-compatible base URLs, keyed by provider.
    # IMPORTANT: every provider that goes through OpenAICompatibleProvider
    # (see backend/services/model_provider.py PROVIDERS map) MUST have an
    # entry here, or get_effective_base_url() falls through to `None` —
    # and the `openai` SDK silently treats base_url=None as "not provided"
    # and defaults to https://api.openai.com/v1. That was the root cause
    # of every non-OpenAI provider quietly calling OpenAI's API.
    _DEFAULT_BASE_URLS = {
        ProviderType.OPENAI:      "https://api.openai.com/v1",
        ProviderType.ANTHROPIC:   "https://api.anthropic.com/v1",
        ProviderType.GEMINI:      "https://generativelanguage.googleapis.com/v1beta/openai/",
        ProviderType.GROQ:        "https://api.groq.com/openai/v1",
        ProviderType.MISTRAL:     "https://api.mistral.ai/v1",
        ProviderType.TOGETHER:    "https://api.together.xyz/v1",
        ProviderType.FIREWORKS:   "https://api.fireworks.ai/inference/v1",
        # Cohere's native /v1 REST API does NOT speak OpenAI's chat-completions
        # schema. The OpenAI-SDK-compatible path is /compatibility/v1.
        ProviderType.COHERE:      "https://api.cohere.ai/compatibility/v1",
        ProviderType.PERPLEXITY:  "https://api.perplexity.ai",
        # api.moonshot.cn is the China-mainland platform. International
        # accounts (platform.moonshot.ai) use a separate key + endpoint —
        # if your users sign up internationally, override api_base_url to
        # "https://api.moonshot.ai/v1" per-config.
        ProviderType.MOONSHOT:    "https://api.moonshot.cn/v1",
        ProviderType.DEEPSEEK:    "https://api.deepseek.com/v1",
        # Singapore/international DashScope endpoint. China-mainland accounts
        # should override api_base_url to "https://dashscope.aliyuncs.com/compatible-mode/v1".
        # API keys are NOT interchangeable across DashScope regions.
        ProviderType.QIANWEN:     "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        ProviderType.ZHIPU:       "https://open.bigmodel.cn/api/paas/v4",
    }

    # Providers with no safe universal default: each user's endpoint is
    # account-specific (Azure resource, AI21 has no confirmed OpenAI-compat
    # endpoint, CUSTOM/OPENAI_COMPATIBLE are explicitly user-supplied).
    # These MUST come from api_base_url (or azure_endpoint) — silently
    # falling back to OpenAI here would be worse than just erroring,
    # since it could send an enterprise key/payload to the wrong vendor.
    _REQUIRES_EXPLICIT_BASE_URL = {
        ProviderType.AI21,
        ProviderType.AZURE_OPENAI,
        ProviderType.CUSTOM,
        ProviderType.OPENAI_COMPATIBLE,
    }

    def get_effective_base_url(self) -> Optional[str]:
        """Get the effective API base URL."""
        # Local provider: always resolve to a local URL, never fall through to OpenAI
        if self.provider == ProviderType.LOCAL:
            return self.local_server_url or self.api_base_url or settings.OLLAMA_BASE_URL

        if self.api_base_url:
            # Users often paste the full chat endpoint (…/v1/chat/completions).
            # The OpenAI SDK appends /models and /chat/completions to the base
            # itself, so the stored base must be the API root. Strip a trailing
            # /chat/completions (or /chat/completions/) so the URL is valid for
            # both listing and generation, and for retroactively fixing configs.
            url = self.api_base_url.rstrip('/')
            if url.lower().endswith('/chat/completions'):
                url = url[: -len('/chat/completions')]
            return url

        if self.provider in self._REQUIRES_EXPLICIT_BASE_URL:
            return None

        return self._DEFAULT_BASE_URLS.get(self.provider)

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
            except Exception:
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
            self.last_error = error[:500]

    def mask_key_for_display(self, raw_key: str):
        """Store masked version."""
        if raw_key and len(raw_key) > 4:
            self.api_key_masked = f"...{raw_key[-4:]}"
        else:
            self.api_key_masked = None


class ModelUsageLog(BaseEntity):
    """Track API usage per configuration."""

    __tablename__ = 'model_usage_logs'

    # Inherited from BaseEntity but this is a log table: many rows per agent,
    # so agentium_id must NOT be unique. Kept nullable to avoid insert failures.
    agentium_id = Column(String(10), nullable=True)

    config_id = Column(String(36), ForeignKey('user_model_configs.id'), nullable=False)

    provider = Column(Enum(ProviderType), nullable=False)
    model_used = Column(String(100), nullable=False)

    request_type = Column(String(50), default="chat")
    total_tokens = Column(Integer, default=0)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)

    latency_ms = Column(Integer, nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)

    cost_usd = Column(Float, nullable=True)
    request_metadata = Column(JSON, default=dict)

    # Relationships
    config = relationship("UserModelConfig", back_populates="usage_logs")
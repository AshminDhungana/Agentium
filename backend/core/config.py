"""
Application configuration management.
Uses pydantic-settings for environment variable handling.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field
from cryptography.fernet import Fernet


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    APP_NAME: str = "Agentium"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1
    
    # Database
    DATABASE_URL: str = Field(
        default="postgresql://agentium:agentium@postgres:5432/agentium",
        env="DATABASE_URL"
    )
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    
    # Redis (Message Bus)
    REDIS_URL: str = Field(
        default="redis://redis:6379/0",
        env="REDIS_URL"
    )
    REDIS_POOL_SIZE: int = 50
    REDIS_TIMEOUT: int = 5  # seconds
    
    # Vector Database (ChromaDB)
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    CHROMA_HOST: Optional[str] = None  # For server mode, default None = embedded
    CHROMA_PORT: int = 8000
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    
    # Message Bus (Phase 1)
    MESSAGE_BUS_ENABLED: bool = True
    MESSAGE_STREAM_MAXLEN: int = 1000  # Max messages per agent inbox
    MESSAGE_TTL_SECONDS: int = 86400  # 24 hours
    
    # Rate Limiting (per tier: msg/sec)
    RATE_LIMIT_HEAD: int = 100     # 0xxxx
    RATE_LIMIT_COUNCIL: int = 20   # 1xxxx
    RATE_LIMIT_LEAD: int = 10      # 2xxxx
    RATE_LIMIT_TASK: int = 5       # 3xxxx
    
    # Security
    SECRET_KEY: str = Field(default="7fcf37764e0d9ab783ceb7a76b71d76fda122aabeaa20062d86e2bb0dfd2d3dd", env="SECRET_KEY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Encryption for API keys - auto-generate valid key if not provided
    # In production, set this via environment variable for persistence
    ENCRYPTION_KEY: str = Field(
        default_factory=lambda: Fernet.generate_key().decode(),
        env="ENCRYPTION_KEY"
    )
    
    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    
    # Monitoring
    HEALTH_CHECK_INTERVAL: int = 300  # seconds
    
    # Phase 9: Alerting (SMTP — skipped if not configured)
    SMTP_HOST: Optional[str] = Field(default=None, env="SMTP_HOST")
    SMTP_PORT: int = Field(default=587, env="SMTP_PORT")
    SMTP_USER: Optional[str] = Field(default=None, env="SMTP_USER")
    SMTP_PASSWORD: Optional[str] = Field(default=None, env="SMTP_PASSWORD")
    ALERT_EMAIL_TO: Optional[str] = Field(default=None, env="ALERT_EMAIL_TO")
    WEBHOOK_ALERT_URL: Optional[str] = Field(default=None, env="WEBHOOK_ALERT_URL")
    
    # Phase 9: Memory Management — retention / archival periods
    AUDIT_LOG_RETENTION_DAYS: int = Field(default=90, env="AUDIT_LOG_RETENTION_DAYS")
    TASK_ARCHIVE_DAYS: int = Field(default=30, env="TASK_ARCHIVE_DAYS")
    CONSTITUTION_MAX_VERSIONS: int = Field(default=10, env="CONSTITUTION_MAX_VERSIONS")
    
    # Phase 9: Security Hardening
    TOKEN_EXPIRY_DAYS: int = Field(default=7, env="TOKEN_EXPIRY_DAYS")
    MAX_CONCURRENT_SESSIONS: int = Field(default=5, env="MAX_CONCURRENT_SESSIONS")
    API_RATE_LIMIT_PER_MINUTE: int = Field(default=100, env="API_RATE_LIMIT_PER_MINUTE")
    
    # Remote Executor (Phase 6.6)
    REMOTE_EXECUTOR_ENABLED: bool = Field(default=True, env="REMOTE_EXECUTOR_ENABLED")
    SANDBOX_TIMEOUT_SECONDS: int = Field(default=300, env="SANDBOX_TIMEOUT_SECONDS")
    SANDBOX_MEMORY_MB: int = Field(default=512, env="SANDBOX_MEMORY_MB")
    SANDBOX_CPU_LIMIT: float = Field(default=1.0, env="SANDBOX_CPU_LIMIT")
    MAX_CONCURRENT_SANDBOXES: int = Field(default=10, env="MAX_CONCURRENT_SANDBOXES")
    SANDBOX_NETWORK_ENABLED: bool = Field(default=False, env="SANDBOX_NETWORK_ENABLED")
    
    # Phase 10.1: Browser Control
    BROWSER_ENABLED: bool = Field(default=True, env="BROWSER_ENABLED")
    BROWSER_TIMEOUT_SECONDS: int = Field(default=30, env="BROWSER_TIMEOUT_SECONDS")
    BROWSER_MAX_CONCURRENT: int = Field(default=5, env="BROWSER_MAX_CONCURRENT")
    BROWSER_BLOCKED_DOMAINS: str = Field(default="", env="BROWSER_BLOCKED_DOMAINS")
    
    # Phase 10.3: Voice Channels
    TWILIO_ACCOUNT_SID: Optional[str] = Field(default=None, env="TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: Optional[str] = Field(default=None, env="TWILIO_AUTH_TOKEN")
    DISCORD_VOICE_ENABLED: bool = Field(default=False, env="DISCORD_VOICE_ENABLED")
    
    # Phase 10.4: Autonomous Learning
    LEARNING_DECAY_DAYS: int = Field(default=30, env="LEARNING_DECAY_DAYS")
    LEARNING_DECAY_RATE: float = Field(default=0.85, env="LEARNING_DECAY_RATE")
    LEARNING_MIN_CONFIDENCE: float = Field(default=0.1, env="LEARNING_MIN_CONFIDENCE")
    
    # Phase 11.2: Federation
    FEDERATION_ENABLED: bool = Field(default=False, env="FEDERATION_ENABLED")
    FEDERATION_INSTANCE_NAME: str = Field(default="Agentium-Primary", env="FEDERATION_INSTANCE_NAME")
    FEDERATION_INSTANCE_URL: str = Field(default="http://localhost:8000", env="FEDERATION_INSTANCE_URL")
    FEDERATION_SHARED_SECRET: str = Field(default="change_me_in_production", env="FEDERATION_SHARED_SECRET")
    FEDERATION_HEARTBEAT_INTERVAL: int = Field(default=300, env="FEDERATION_HEARTBEAT_INTERVAL")  # seconds
    FEDERATION_STALE_TIMEOUT_MINUTES: int = Field(default=1440, env="FEDERATION_STALE_TIMEOUT_MINUTES")  # 24h
    
    # Phase 11.4: Mobile Push Notifications
    FCM_SERVER_KEY: Optional[str] = Field(default=None, env="FCM_SERVER_KEY")
    APNS_KEY_ID: Optional[str] = Field(default=None, env="APNS_KEY_ID")
    APNS_TEAM_ID: Optional[str] = Field(default=None, env="APNS_TEAM_ID")
    APNS_KEY_PATH: Optional[str] = Field(default=None, env="APNS_KEY_PATH")
    APNS_BUNDLE_ID: str = Field(default="com.agentium.app", env="APNS_BUNDLE_ID")
    PUSH_NOTIFICATION_ENABLED: bool = Field(default=False, env="PUSH_NOTIFICATION_ENABLED")
    
    @property
    def cors_origins(self) -> list:
        """Parse CORS origins string to list."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
    
    class Config:
        # env_file = ".env"  # Disabled - use Docker environment variables only
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
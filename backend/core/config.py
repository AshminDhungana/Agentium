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
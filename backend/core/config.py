from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    APP_NAME: str = "Agentium"
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    class Config:
        env_file = ".env"
        extra = "ignore" 

settings = Settings()

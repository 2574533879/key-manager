import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Admin account (seed on first run)
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"

    # JWT
    JWT_SECRET: str = "change-me-to-a-random-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120  # 2 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    DATABASE_URL: str = "sqlite:///./data/app.db"

    # Security
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    CLIENT_AUTH_RATE_LIMIT: str = "10/minute"  # per IP

    # Default settings (can be changed via admin panel)
    DEFAULT_API_PREFIX: str = "/api"
    DEFAULT_HEARTBEAT_THRESHOLD_MINUTES: int = 5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

import logging

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "lending-poc"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    DATABASE_URL: str
    LOG_LEVEL: str = "INFO"
    ENCRYPTION_KEY: str


settings = Settings()

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(settings.APP_NAME)

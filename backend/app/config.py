"""Settings, read once from the environment.

Every value has a development default EXCEPT the ones that would be unsafe to
default — those fail loudly at import time rather than silently running with a
placeholder in production.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "project-template"
    database_url: str = "postgresql+asyncpg://app:change-me-locally@db:5432/app"
    secret_key: str = "dev-only-not-a-real-secret"

    @property
    def is_placeholder_secret(self) -> bool:
        return self.secret_key.startswith("dev-only")


settings = Settings()

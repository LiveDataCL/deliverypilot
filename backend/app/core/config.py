from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "dev"

    # Runtime role (app + tests) — deliberately NOT the bootstrap superuser.
    # See db/init/01-create-app-role.sql for why.
    database_url: str
    test_database_url: str | None = None
    # Migrations-only role (bootstrap superuser) — owns every table, needed
    # for CREATE TABLE/TYPE, ALTER TABLE ... FORCE ROW LEVEL SECURITY, and
    # CREATE POLICY. Never used for regular application queries.
    migrations_database_url: str
    test_migrations_database_url: str | None = None
    redis_url: str

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    fcm_credentials_json: str | None = None

    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket: str | None = None
    r2_endpoint: str | None = None

    sentry_dsn: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

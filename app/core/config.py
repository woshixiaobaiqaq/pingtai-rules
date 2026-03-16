from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="platform-content-audit", alias="APP_NAME")
    app_env: str = Field(default="local", alias="APP_ENV")
    debug: bool = Field(default=True, alias="APP_DEBUG")
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/platform_content_audit",
        alias="DATABASE_URL",
    )
    pgvector_dimension: int = Field(default=64, alias="PGVECTOR_DIMENSION")
    embedding_model: str = Field(default="hashing-v1", alias="EMBEDDING_MODEL")
    default_vector_limit: int = Field(default=12, alias="DEFAULT_VECTOR_LIMIT")
    default_rule_limit: int = Field(default=20, alias="DEFAULT_RULE_LIMIT")
    default_target_platforms: str = Field(
        default="douyin,xiaohongshu",
        alias="DEFAULT_TARGET_PLATFORMS",
    )
    rule_source_mode: str = Field(default="file", alias="RULE_SOURCE_MODE")
    local_rule_manifest_path: str = Field(
        default="data/rule_library/manifest.json",
        alias="LOCAL_RULE_MANIFEST_PATH",
    )

    @property
    def default_target_platform_list(self) -> list[str]:
        return [item.strip() for item in self.default_target_platforms.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

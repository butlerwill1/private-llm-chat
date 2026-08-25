"""Validated application configuration loaded from ``CHAT_*`` environment variables."""

import base64
import binascii
import os
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelBackend(StrEnum):
    OPENROUTER = "openrouter"
    SELF_HOSTED = "self_hosted"


class StorageBackend(StrEnum):
    LOCAL = "local"
    MEMORY = "memory"
    S3 = "s3"


class LocalKeyMode(StrEnum):
    DPAPI = "dpapi"
    ENVIRONMENT = "environment"


class OpenRouterRoute(BaseModel):
    """One immutable model/provider boundary for a privacy-restricted request."""

    model_config = {"frozen": True, "extra": "forbid"}
    model_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    label: str = Field(min_length=1)


DEFAULT_OPENROUTER_ROUTES: tuple[OpenRouterRoute, ...] = (
    OpenRouterRoute(
        model_id="meta-llama/llama-3.3-70b-instruct", provider="deepinfra", label="Llama 3.3 70B"
    ),
    OpenRouterRoute(model_id="qwen/qwen3-32b", provider="deepinfra", label="Qwen3 32B"),
    OpenRouterRoute(model_id="google/gemma-3-27b-it", provider="deepinfra", label="Gemma 3 27B"),
    OpenRouterRoute(
        model_id="mistralai/mistral-small-3.2-24b-instruct",
        provider="deepinfra",
        label="Mistral Small 3.2 24B",
    ),
    OpenRouterRoute(model_id="deepseek/deepseek-r1", provider="novita", label="DeepSeek R1"),
)


class Settings(BaseSettings):
    """Configuration that fails closed instead of selecting a plaintext fallback."""

    model_config = SettingsConfigDict(env_prefix="CHAT_", env_file=".env", extra="ignore")

    environment: str = "development"
    model_backend: ModelBackend = ModelBackend.OPENROUTER
    model_name: str = DEFAULT_OPENROUTER_ROUTES[0].model_id
    storage_backend: StorageBackend = StorageBackend.LOCAL
    local_data_dir: Path | None = None
    local_key_mode: LocalKeyMode = LocalKeyMode.DPAPI
    local_master_key_b64: SecretStr | None = None
    conversation_bucket: str | None = None
    kms_key_id: str | None = None
    aws_region: str = "eu-west-2"
    self_hosted_base_url: str = "http://127.0.0.1:11434/v1"
    self_hosted_api_key: SecretStr | None = None
    model_response_timeout_seconds: int = Field(default=300, ge=1, le=900)
    openrouter_api_key: SecretStr | None = None
    enable_openrouter: bool = True
    openrouter_routes: tuple[OpenRouterRoute, ...] = DEFAULT_OPENROUTER_ROUTES
    openrouter_zdr_preflight: bool = True
    openrouter_max_output_tokens: int = Field(default=4096, ge=1, le=4096)
    allow_custom_openrouter_model: bool = False

    @field_validator("local_master_key_b64")
    @classmethod
    def validate_master_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        try:
            decoded = base64.b64decode(value.get_secret_value(), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Master key must be valid base64") from exc
        if len(decoded) != 32:
            raise ValueError("Decoded master key must contain exactly 32 bytes")
        return value

    @field_validator("openrouter_routes")
    @classmethod
    def require_unique_routes(
        cls, value: tuple[OpenRouterRoute, ...]
    ) -> tuple[OpenRouterRoute, ...]:
        if not value:
            raise ValueError("At least one OpenRouter route is required")
        if len({route.model_id for route in value}) != len(value):
            raise ValueError("OpenRouter route model IDs must be unique")
        return value

    @model_validator(mode="after")
    def validate_configuration(self) -> "Settings":
        if self.storage_backend is StorageBackend.MEMORY and self.local_master_key_b64 is None:
            raise ValueError("CHAT_LOCAL_MASTER_KEY_B64 is required for memory storage")
        if self.storage_backend is StorageBackend.LOCAL:
            if self.local_key_mode is LocalKeyMode.DPAPI and os.name != "nt":
                raise ValueError("CHAT_LOCAL_KEY_MODE=dpapi requires Windows")
            if (
                self.local_key_mode is LocalKeyMode.ENVIRONMENT
                and self.local_master_key_b64 is None
            ):
                raise ValueError(
                    "CHAT_LOCAL_MASTER_KEY_B64 is required for environment local storage"
                )
        if self.storage_backend is StorageBackend.S3 and (
            self.conversation_bucket is None or self.kms_key_id is None
        ):
            raise ValueError(
                "CHAT_CONVERSATION_BUCKET and CHAT_KMS_KEY_ID are required for S3 storage"
            )
        if self.enable_openrouter or self.model_backend is ModelBackend.OPENROUTER:
            if self.openrouter_api_key is None:
                raise ValueError("CHAT_OPENROUTER_API_KEY is required for OpenRouter mode")
            key = self.openrouter_api_key.get_secret_value().strip()
            if not key or key.startswith("REPLACE_"):
                raise ValueError("CHAT_OPENROUTER_API_KEY must contain a real OpenRouter API key")
        return self

    def local_master_key(self) -> bytes:
        if self.local_master_key_b64 is None:
            raise RuntimeError("Local master key is unavailable for the selected storage backend")
        return base64.b64decode(self.local_master_key_b64.get_secret_value(), validate=True)

    def resolved_local_data_dir(self) -> Path:
        if self.local_data_dir is not None:
            return self.local_data_dir
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise RuntimeError(
                "LOCALAPPDATA is required for the default local transcript directory"
            )
        return Path(local_app_data) / "PrivateLLMChat"

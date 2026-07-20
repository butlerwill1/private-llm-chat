import base64
import binascii
from enum import StrEnum

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelBackend(StrEnum):
    OPENROUTER = "openrouter"
    SELF_HOSTED = "self_hosted"


class Settings(BaseSettings):
    """Environment-only secrets keep credentials out of source and generated schemas."""

    model_config = SettingsConfigDict(env_prefix="CHAT_", env_file=".env", extra="ignore")
    environment: str = "development"
    model_backend: ModelBackend = ModelBackend.SELF_HOSTED
    local_master_key_b64: SecretStr
    self_hosted_base_url: str = "http://127.0.0.1:11434/v1"
    self_hosted_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    openrouter_allowed_providers: tuple[str, ...] = ()

    @field_validator("local_master_key_b64")
    @classmethod
    def validate_master_key(cls, value: SecretStr) -> SecretStr:
        try:
            decoded = base64.b64decode(value.get_secret_value(), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Master key must be valid base64") from exc
        if len(decoded) != 32:
            raise ValueError("Decoded master key must contain exactly 32 bytes")
        return value

    def local_master_key(self) -> bytes:
        return base64.b64decode(self.local_master_key_b64.get_secret_value(), validate=True)


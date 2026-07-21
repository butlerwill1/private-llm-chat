"""Validated application configuration loaded from environment variables."""

import base64
import binascii
from enum import StrEnum

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelBackend(StrEnum):
    """Inference implementations understood by the composition root."""

    OPENROUTER = "openrouter"
    SELF_HOSTED = "self_hosted"


class StorageBackend(StrEnum):
    """Persistence implementations selected at the composition root."""

    MEMORY = "memory"
    S3 = "s3"


class Settings(BaseSettings):
    """Typed settings populated from ``CHAT_*`` environment variables.

    Pydantic Settings validates configuration once during application startup. Secrets
    use ``SecretStr`` so ordinary representations do not accidentally reveal them.
    """

    # Unknown environment values are ignored because a process may contain unrelated
    # variables, while the CHAT_ prefix prevents collisions with generic setting names.
    model_config = SettingsConfigDict(env_prefix="CHAT_", env_file=".env", extra="ignore")
    environment: str = "development"
    model_backend: ModelBackend = ModelBackend.SELF_HOSTED
    model_name: str = "private-chat"
    storage_backend: StorageBackend = StorageBackend.MEMORY
    local_master_key_b64: SecretStr | None = None
    conversation_bucket: str | None = None
    kms_key_id: str | None = None
    aws_region: str = "eu-west-2"
    self_hosted_base_url: str = "http://127.0.0.1:11434/v1"
    self_hosted_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    openrouter_allowed_providers: tuple[str, ...] = ()

    @field_validator("local_master_key_b64")
    @classmethod
    def validate_master_key(cls, value: SecretStr | None) -> SecretStr | None:
        """Fail during startup unless the local development key is exactly 256 bits."""

        if value is None:
            return None

        try:
            decoded = base64.b64decode(value.get_secret_value(), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Master key must be valid base64") from exc
        if len(decoded) != 32:
            raise ValueError("Decoded master key must contain exactly 32 bytes")
        return value

    @model_validator(mode="after")
    def validate_storage_configuration(self) -> "Settings":
        """Require exactly the credentials needed by the selected storage adapter."""

        if self.storage_backend is StorageBackend.MEMORY and self.local_master_key_b64 is None:
            raise ValueError("CHAT_LOCAL_MASTER_KEY_B64 is required for memory storage")
        if self.storage_backend is StorageBackend.S3:
            if self.conversation_bucket is None or self.kms_key_id is None:
                raise ValueError(
                    "CHAT_CONVERSATION_BUCKET and CHAT_KMS_KEY_ID are required for S3 storage"
                )
        return self

    def local_master_key(self) -> bytes:
        """Decode the already-validated local key at the composition boundary."""

        if self.local_master_key_b64 is None:
            raise RuntimeError("Local master key is unavailable for the selected storage backend")
        return base64.b64decode(self.local_master_key_b64.get_secret_value(), validate=True)

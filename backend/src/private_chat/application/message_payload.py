"""Versioned, encrypted message contents and turn-usage metadata."""

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from private_chat.domain.models import CostBasis, TurnUsage


@dataclass(frozen=True, slots=True)
class DecryptedMessagePayload:
    content: str
    usage: TurnUsage | None


def encode_message_payload(content: str, usage: TurnUsage | None) -> bytes:
    """Encode new messages before application-level encryption."""

    usage_record: dict[str, Any] | None = None
    if usage is not None:
        usage_record = {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "cached_input_tokens": usage.cached_input_tokens,
            "cache_write_input_tokens": usage.cache_write_input_tokens,
            "reasoning_tokens": usage.reasoning_tokens,
            "cost_usd": None if usage.cost_usd is None else str(usage.cost_usd),
            "cost_basis": usage.cost_basis.value,
            "model": usage.model,
            "provider": usage.provider,
        }
    return json.dumps(
        {"schema_version": 1, "content": content, "usage": usage_record},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()


def _optional_tokens(record: dict[str, Any], name: str) -> int | None:
    value = record.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Invalid encrypted usage field: {name}")
    return int(value)


def _decode_usage(value: Any) -> TurnUsage | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Invalid encrypted usage record")
    cost_value = value.get("cost_usd")
    if cost_value is not None and not isinstance(cost_value, str):
        raise ValueError("Invalid encrypted usage cost")
    try:
        cost = None if cost_value is None else Decimal(cost_value)
        basis = CostBasis(value["cost_basis"])
    except (InvalidOperation, KeyError, ValueError) as error:
        raise ValueError("Invalid encrypted usage record") from error
    model = value.get("model")
    provider = value.get("provider")
    if not isinstance(model, str) or not model or not isinstance(provider, str) or not provider:
        raise ValueError("Invalid encrypted usage provenance")
    return TurnUsage(
        input_tokens=_optional_tokens(value, "input_tokens"),
        output_tokens=_optional_tokens(value, "output_tokens"),
        total_tokens=_optional_tokens(value, "total_tokens"),
        cached_input_tokens=_optional_tokens(value, "cached_input_tokens"),
        cache_write_input_tokens=_optional_tokens(value, "cache_write_input_tokens"),
        reasoning_tokens=_optional_tokens(value, "reasoning_tokens"),
        cost_usd=cost,
        cost_basis=basis,
        model=model,
        provider=provider,
    )


def decode_message_payload(plaintext: bytes) -> DecryptedMessagePayload:
    """Decode a new payload or retain a legacy plaintext message without usage."""

    text = plaintext.decode()
    try:
        record = json.loads(text)
    except json.JSONDecodeError:
        return DecryptedMessagePayload(content=text, usage=None)
    if not isinstance(record, dict) or record.get("schema_version") != 1:
        return DecryptedMessagePayload(content=text, usage=None)
    content = record.get("content")
    if not isinstance(content, str):
        raise ValueError("Invalid encrypted message payload")
    return DecryptedMessagePayload(content=content, usage=_decode_usage(record.get("usage")))

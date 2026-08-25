"""Strict normalisation of OpenAI-compatible provider usage records."""

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from private_chat.domain.models import CostBasis, TurnUsage


def _required_token(record: Mapping[str, Any], name: str) -> int:
    value = record.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Invalid usage token field: {name}")
    return value


def _optional_token(record: Mapping[str, Any], name: str) -> int | None:
    value = record.get(name)
    if value is None:
        return None
    return _required_token(record, name)


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Invalid usage cost")
    try:
        cost = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Invalid usage cost") from error
    if cost < 0:
        raise ValueError("Invalid usage cost")
    return cost


def parse_openrouter_usage(
    value: Any, *, model: str, provider: str
) -> TurnUsage | None:
    """Parse the exact cost and native token totals attached to a completion."""

    if not isinstance(value, Mapping):
        return None
    try:
        details = value.get("prompt_tokens_details")
        completion_details = value.get("completion_tokens_details")
        return TurnUsage(
            input_tokens=_required_token(value, "prompt_tokens"),
            output_tokens=_required_token(value, "completion_tokens"),
            total_tokens=_required_token(value, "total_tokens"),
            cached_input_tokens=(
                None
                if not isinstance(details, Mapping)
                else _optional_token(details, "cached_tokens")
            ),
            cache_write_input_tokens=(
                None
                if not isinstance(details, Mapping)
                else _optional_token(details, "cache_write_tokens")
            ),
            reasoning_tokens=(
                None
                if not isinstance(completion_details, Mapping)
                else _optional_token(completion_details, "reasoning_tokens")
            ),
            cost_usd=_decimal(value.get("cost")),
            cost_basis=CostBasis.PROVIDER_REPORTED,
            model=model,
            provider=provider,
        )
    except ValueError:
        return None


def parse_generation_usage(value: Any, *, model: str, provider: str) -> TurnUsage | None:
    """Normalise OpenRouter's generation-record fallback representation."""

    data = value.get("data") if isinstance(value, Mapping) else None
    if not isinstance(data, Mapping):
        return None
    try:
        input_tokens = _required_token(data, "tokens_prompt")
        output_tokens = _required_token(data, "tokens_completion")
        return TurnUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cached_input_tokens=_optional_token(data, "native_tokens_cached"),
            cache_write_input_tokens=None,
            reasoning_tokens=_optional_token(data, "native_tokens_reasoning"),
            cost_usd=_decimal(data.get("total_cost", data.get("usage"))),
            cost_basis=CostBasis.PROVIDER_REPORTED,
            model=model,
            provider=provider,
        )
    except ValueError:
        return None


def parse_self_hosted_usage(value: Any, *, model: str, provider: str) -> TurnUsage | None:
    """Normalise token totals without pretending locally hosted inference is free."""

    if not isinstance(value, Mapping):
        return None
    try:
        details = value.get("prompt_tokens_details")
        completion_details = value.get("completion_tokens_details")
        return TurnUsage(
            input_tokens=_required_token(value, "prompt_tokens"),
            output_tokens=_required_token(value, "completion_tokens"),
            total_tokens=_required_token(value, "total_tokens"),
            cached_input_tokens=(
                None
                if not isinstance(details, Mapping)
                else _optional_token(details, "cached_tokens")
            ),
            cache_write_input_tokens=(
                None
                if not isinstance(details, Mapping)
                else _optional_token(details, "cache_write_tokens")
            ),
            reasoning_tokens=(
                None
                if not isinstance(completion_details, Mapping)
                else _optional_token(completion_details, "reasoning_tokens")
            ),
            cost_usd=None,
            cost_basis=CostBasis.SELF_HOSTED_UNALLOCATED,
            model=model,
            provider=provider,
        )
    except ValueError:
        return None

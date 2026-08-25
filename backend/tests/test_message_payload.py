"""Usage metadata remains encrypted and legacy messages keep loading."""

from decimal import Decimal

from private_chat.application.message_payload import decode_message_payload, encode_message_payload
from private_chat.domain.models import CostBasis, TurnUsage


def test_usage_payload_round_trip_preserves_decimal_cost() -> None:
    usage = TurnUsage(
        input_tokens=1284,
        output_tokens=96,
        total_tokens=1380,
        cached_input_tokens=1024,
        cache_write_input_tokens=0,
        reasoning_tokens=18,
        cost_usd=Decimal("0.00234100"),
        cost_basis=CostBasis.PROVIDER_REPORTED,
        model="provider/model",
        provider="provider",
    )

    decoded = decode_message_payload(encode_message_payload("Private message", usage))

    assert decoded.content == "Private message"
    assert decoded.usage == usage
    assert b"0.00234100" in encode_message_payload("Private message", usage)


def test_legacy_raw_content_remains_readable_without_usage() -> None:
    decoded = decode_message_payload(b"Original encrypted message body")
    assert decoded.content == "Original encrypted message body"
    assert decoded.usage is None

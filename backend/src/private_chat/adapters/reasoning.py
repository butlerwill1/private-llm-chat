"""Extract provider-exposed reasoning text without rendering opaque reasoning data."""

from collections.abc import Mapping
from typing import Any


def reasoning_text(message: Mapping[str, Any]) -> str:
    # Some providers send the same text in both the simple and structured fields.
    for name in ("reasoning", "reasoning_content"):
        value = message.get(name)
        if isinstance(value, str) and value:
            return value
    details = message.get("reasoning_details")
    if not isinstance(details, list):
        return ""
    pieces: list[str] = []
    for detail in details:
        if not isinstance(detail, Mapping):
            continue
        kind = detail.get("type")
        if not isinstance(kind, str):
            continue
        field = {"reasoning.text": "text", "reasoning.summary": "summary"}.get(kind)
        if field is not None:
            value = detail.get(field)
            if isinstance(value, str):
                pieces.append(value)
    return "".join(pieces)

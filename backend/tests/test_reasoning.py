from private_chat.adapters.reasoning import reasoning_text


def test_only_readable_reasoning_is_extracted_without_duplicate_fields() -> None:
    details = [
        {"type": "reasoning.encrypted", "data": "opaque", "text": "not readable"},
        {"type": "reasoning.summary", "summary": "Summary"},
        {"type": "reasoning.text", "text": " text"},
        {"type": [], "text": "invalid"},
    ]
    assert reasoning_text({"reasoning_details": details}) == "Summary text"
    assert reasoning_text({"reasoning": "Preferred", "reasoning_details": details}) == "Preferred"
    encrypted_only = {"reasoning_details": [{"type": "reasoning.encrypted", "data": "x"}]}
    assert reasoning_text(encrypted_only) == ""

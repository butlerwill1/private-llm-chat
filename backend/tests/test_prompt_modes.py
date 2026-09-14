import json
from pathlib import Path

import httpx
import pytest
from test_api import make_settings
from test_model_selection import RecordingModel

from private_chat.adapters.conversation_instructions import (
    STANDARD_PROMPT,
    FileConversationInstructionsProvider,
)
from private_chat.bootstrap import create_app
from private_chat.domain.models import Role


@pytest.mark.asyncio
async def test_private_modes_are_selected_without_entering_the_transcript(tmp_path: Path) -> None:
    (tmp_path / "custom.json").write_text(
        json.dumps({"label": "Custom", "prompt": "Private test instructions."}), encoding="utf-8"
    )
    settings = make_settings().model_copy(
        update={"prompt_modes_dir": tmp_path, "instructions_file": None}
    )
    model = RecordingModel()
    app = create_app(settings, model_client=model)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        config = await client.get("/v1/model-configuration")
        assert config.json()["prompt_modes"] == [
            {"id": "standard", "label": "Standard"}, {"id": "custom", "label": "Custom"}
        ]
        assert "Private test instructions" not in config.text
        created = await client.post("/v1/conversations")
        url = f"/v1/conversations/{created.json()['id']}/messages"
        for mode in ("custom", "standard"):
            response = await client.post(url, json={"content": "hello", "prompt_mode_id": mode})
            assert response.status_code == 200
            assert all(message["role"] != "system" for message in response.json()["messages"])
        assert model.requests[0].messages[0].content == "Private test instructions."
        assert model.requests[1].messages[0].content == STANDARD_PROMPT
        assert sum(message.role is Role.SYSTEM for message in model.requests[1].messages) == 1
        for invalid in ("missing", "../custom"):
            response = await client.post(url, json={"content": "hello", "prompt_mode_id": invalid})
            assert response.status_code == 422
        assert len(model.requests) == 2


def test_invalid_modes_cannot_replace_standard(tmp_path: Path) -> None:
    for name, content in {
        "broken": "{", "empty": '{"label":"Empty","prompt":" "}',
        "standard": '{"label":"Override","prompt":"private"}',
    }.items():
        (tmp_path / f"{name}.json").write_text(content, encoding="utf-8")
    provider = FileConversationInstructionsProvider(None, tmp_path)
    assert provider.options() == ({"id": "standard", "label": "Standard"},)
    assert provider.instructions("standard") == STANDARD_PROMPT

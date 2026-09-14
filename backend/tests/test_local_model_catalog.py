"""Verify that named dropdown choices select the installed Ollama presets."""

import base64
import json

import httpx
import pytest

from private_chat.bootstrap import create_app
from private_chat.config import ModelBackend, Settings, StorageBackend


@pytest.mark.asyncio
async def test_local_dropdown_models_route_to_their_exact_ollama_tags() -> None:
    requested_models: list[str] = []

    def ollama(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://127.0.0.1:11434/v1/chat/completions"
        payload = json.loads(request.content)
        requested_models.append(payload["model"])
        return httpx.Response(
            200,
            json={
                "model": payload["model"],
                "choices": [{"message": {"content": "ready"}}],
            },
        )

    settings = Settings(
        _env_file=None,
        model_backend=ModelBackend.SELF_HOSTED,
        model_name="gemma3:4b",
        enable_local_ollama=True,
        enable_openrouter=False,
        telemetry_enabled=False,
        instructions_file=None,
        prompt_modes_dir=None,
        storage_backend=StorageBackend.MEMORY,
        local_master_key_b64=base64.b64encode(b"x" * 32).decode(),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(ollama)) as inference:
        app = create_app(settings, http_client=inference)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as browser:
            options = (await browser.get("/v1/models")).json()
            assert [(option["id"], option["label"]) for option in options] == [
                ("gemma3:4b", "Gemma 3 4B — Local GPU (auto)"),
                ("qwen3.5:9b-laptop", "Qwen 3.5 9B — Local GPU (auto)"),
                ("qwen3.6:27b-cpu", "Qwen 3.6 27B — Local CPU"),
            ]
            created = await browser.post("/v1/conversations")
            conversation_id = created.json()["id"]
            for model_id in ("qwen3.5:9b-laptop", "qwen3.6:27b-cpu", "gemma3:4b"):
                changed = await browser.patch(
                    f"/v1/conversations/{conversation_id}/model", json={"model_id": model_id}
                )
                assert changed.status_code == 200
                assert changed.json()["active_model_id"] == model_id
                turn = await browser.post(
                    f"/v1/conversations/{conversation_id}/messages", json={"content": "hello"}
                )
                assert turn.status_code == 200
            assert requested_models == ["qwen3.5:9b-laptop", "qwen3.6:27b-cpu", "gemma3:4b"]


def test_duplicate_local_model_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="Local Ollama route model IDs must be unique"):
        Settings(
            _env_file=None,
            local_ollama_routes=[
                {"model_id": "same-model", "label": "One"},
                {"model_id": "same-model", "label": "Two"},
            ],
        )

import base64
from uuid import uuid4

import httpx
import pytest

from private_chat.bootstrap import create_app
from private_chat.config import Settings
from private_chat.domain.models import ModelRequest, ModelResponse


class StubModel:
    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse("hello", request.model, "stub")


@pytest.mark.asyncio
async def test_api_validates_and_returns_a_turn() -> None:
    settings = Settings(
        local_master_key_b64=base64.b64encode(b"x" * 32).decode(),
    )
    app = create_app(settings, model_client=StubModel())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/v1/conversations/{uuid4()}/messages",
            json={"content": "hello", "model": "local"},
        )
    assert response.status_code == 200
    assert response.json()["content"] == "hello"
    assert response.json()["role"] == "assistant"


@pytest.mark.asyncio
async def test_api_forbids_unexpected_fields() -> None:
    settings = Settings(local_master_key_b64=base64.b64encode(b"x" * 32).decode())
    app = create_app(settings, model_client=StubModel())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/v1/conversations/{uuid4()}/messages",
            json={"content": "hello", "model": "local", "admin": True},
        )
    assert response.status_code == 422

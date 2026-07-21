import base64

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
        created = await client.post("/v1/conversations")
        conversation_id = created.json()["id"]
        response = await client.post(
            f"/v1/conversations/{conversation_id}/messages",
            json={"content": "hello"},
        )
    assert response.status_code == 200
    assert [message["content"] for message in response.json()["messages"]] == [
        "hello",
        "hello",
    ]
    assert response.json()["messages"][-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_api_forbids_unexpected_fields() -> None:
    settings = Settings(local_master_key_b64=base64.b64encode(b"x" * 32).decode())
    app = create_app(settings, model_client=StubModel())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/v1/conversations")
        response = await client.post(
            f"/v1/conversations/{created.json()['id']}/messages",
            json={"content": "hello", "admin": True},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_conversation_lifecycle() -> None:
    settings = Settings(local_master_key_b64=base64.b64encode(b"x" * 32).decode())
    app = create_app(settings, model_client=StubModel())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        empty = await client.get("/v1/conversations")
        created = await client.post("/v1/conversations")
        conversation_id = created.json()["id"]
        listed = await client.get("/v1/conversations")
        deleted = await client.delete(f"/v1/conversations/{conversation_id}")
        missing = await client.get(f"/v1/conversations/{conversation_id}")

    assert empty.json() == []
    assert created.status_code == 201
    assert listed.json()[0]["id"] == conversation_id
    assert deleted.status_code == 204
    assert missing.status_code == 404

"""HTTP-boundary tests for FastAPI request validation and conversation routes.

These tests run the application in-process through HTTPX's ASGI transport. They
exercise the same routing, Pydantic validation and dependency wiring used by a
real server without opening a network port or contacting an inference provider.
"""

import base64

import httpx
import pytest

from private_chat.bootstrap import create_app
from private_chat.config import Settings
from private_chat.domain.models import ModelRequest, ModelResponse


class StubModel:
    """Deterministic model double that makes API assertions independent of Ollama."""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Return a fixed answer while preserving the requested model metadata."""

        return ModelResponse("hello", request.model, "stub")


@pytest.mark.asyncio
async def test_api_validates_and_returns_a_turn() -> None:
    """A valid message should produce a complete user-and-assistant transcript.

    This covers conversation creation, JSON request validation, use-case
    execution and response serialisation through the public HTTP contract.
    """

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
    # The endpoint returns the authoritative conversation rather than only the
    # newly generated message, allowing the frontend to replace local state.
    assert response.status_code == 200
    assert [message["content"] for message in response.json()["messages"]] == [
        "hello",
        "hello",
    ]
    assert response.json()["messages"][-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_api_forbids_unexpected_fields() -> None:
    """Unknown JSON properties should be rejected instead of silently ignored.

    Failing closed at the transport boundary catches client/server contract
    drift and prevents callers from believing unsupported controls were applied.
    """

    settings = Settings(local_master_key_b64=base64.b64encode(b"x" * 32).decode())
    app = create_app(settings, model_client=StubModel())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/v1/conversations")
        response = await client.post(
            f"/v1/conversations/{created.json()['id']}/messages",
            json={"content": "hello", "admin": True},
        )
    # FastAPI uses 422 for a body that cannot satisfy the Pydantic schema.
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_conversation_lifecycle() -> None:
    """Create, list, delete and subsequent lookup should form a coherent lifecycle.

    The final 404 is particularly important for privacy: a successful delete
    must make the conversation unavailable through the application API.
    """

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

    # Assert every state transition separately so failures identify which route
    # broke rather than merely reporting a mismatched final response.
    assert empty.json() == []
    assert created.status_code == 201
    assert listed.json()[0]["id"] == conversation_id
    assert deleted.status_code == 204
    assert missing.status_code == 404

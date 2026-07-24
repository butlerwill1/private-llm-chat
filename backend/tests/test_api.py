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

        # The production object would call Ollama or OpenRouter. This test double
        # immediately returns predictable data so the test exercises only our API.
        return ModelResponse("hello", request.model, "stub")


class TimingOutModel:
    """Model double that simulates a tunnel or inference response timeout."""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Raise the same HTTPX exception produced by the real model adapter."""

        # The route must translate infrastructure timeouts into a useful HTTP
        # response instead of returning an unhandled 500 to the browser.
        raise httpx.ReadTimeout("model response exceeded the configured timeout")


@pytest.mark.asyncio
async def test_api_validates_and_returns_a_turn() -> None:
    """A valid message should produce a complete user-and-assistant transcript.

    This covers conversation creation, JSON request validation, use-case
    execution and response serialisation through the public HTTP contract.
    """

    # Arrange: Settings normally reads CHAT_* environment variables. Supplying a
    # base64-encoded 32-byte key directly makes this test self-contained.
    settings = Settings(
        local_master_key_b64=base64.b64encode(b"x" * 32).decode(),
    )
    # Build the real FastAPI application, replacing only its model dependency.
    app = create_app(settings, model_client=StubModel())
    # ASGITransport sends HTTPX requests straight into FastAPI in memory. No web
    # server or TCP port is started, but routing and validation still run normally.
    transport = httpx.ASGITransport(app=app)
    # AsyncClient is closed automatically when this block finishes.
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Act, step 1: create the aggregate that the message must belong to.
        created = await client.post("/v1/conversations")
        # Decode the JSON response and retain its generated UUID for the next URL.
        conversation_id = created.json()["id"]
        # Act, step 2: submit a JSON request through the real message endpoint.
        response = await client.post(
            f"/v1/conversations/{conversation_id}/messages",
            json={"content": "hello"},
        )
    # Assert: the endpoint returns the authoritative conversation rather than only the
    # newly generated message, allowing the frontend to replace local state.
    assert response.status_code == 200
    # The list comprehension visits each response message and extracts `content`.
    # The two "hello" values are the submitted user text and StubModel's answer.
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

    # Arrange the same real application and in-memory HTTP client used above.
    settings = Settings(local_master_key_b64=base64.b64encode(b"x" * 32).decode())
    app = create_app(settings, model_client=StubModel())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # A conversation is required so a 404 cannot hide the validation result.
        created = await client.post("/v1/conversations")
        # Act: `admin` is deliberately not part of SendMessageRequest.
        response = await client.post(
            f"/v1/conversations/{created.json()['id']}/messages",
            json={"content": "hello", "admin": True},
        )
    # FastAPI uses 422 for a body that cannot satisfy the Pydantic schema.
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_api_reports_model_timeout_as_gateway_timeout() -> None:
    """A slow local model should produce a retryable 504 rather than a 500.

    The in-memory transport calls the complete FastAPI route while TimingOutModel
    avoids a real GPU request. This keeps the test deterministic and proves the
    browser receives a meaningful status code for this operational failure.
    """

    settings = Settings(local_master_key_b64=base64.b64encode(b"x" * 32).decode())
    app = create_app(settings, model_client=TimingOutModel())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/v1/conversations")
        response = await client.post(
            f"/v1/conversations/{created.json()['id']}/messages",
            json={"content": "hello"},
        )

    assert response.status_code == 504
    assert response.json()["detail"] == (
        "The local model did not respond before the inference timeout."
    )


@pytest.mark.asyncio
async def test_conversation_lifecycle() -> None:
    """Create, list, delete and subsequent lookup should form a coherent lifecycle.

    The final 404 is particularly important for privacy: a successful delete
    must make the conversation unavailable through the application API.
    """

    # Arrange a fresh application. Its in-memory repository starts empty and is
    # isolated from the application created by every other test.
    settings = Settings(local_master_key_b64=base64.b64encode(b"x" * 32).decode())
    app = create_app(settings, model_client=StubModel())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Act: capture every response while moving through the resource lifecycle.
        empty = await client.get("/v1/conversations")
        created = await client.post("/v1/conversations")
        # The server chooses the UUID, so read it before constructing later URLs.
        conversation_id = created.json()["id"]
        listed = await client.get("/v1/conversations")
        deleted = await client.delete(f"/v1/conversations/{conversation_id}")
        # Attempting a read after deletion checks externally observable absence.
        missing = await client.get(f"/v1/conversations/{conversation_id}")

    # Assert every state transition separately so failures identify which route
    # broke rather than merely reporting a mismatched final response.
    assert empty.json() == []
    assert created.status_code == 201
    assert listed.json()[0]["id"] == conversation_id
    assert deleted.status_code == 204
    assert missing.status_code == 404

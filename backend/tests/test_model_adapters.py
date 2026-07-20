from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from private_chat.adapters.openrouter import OpenRouterConfiguration, OpenRouterModelClient
from private_chat.adapters.self_hosted import SelfHostedConfiguration, SelfHostedModelClient
from private_chat.domain.models import ChatMessage, ModelRequest, Role


def request() -> ModelRequest:
    return ModelRequest(
        messages=(ChatMessage(Role.USER, "private prompt", uuid4(), datetime.now(UTC)),),
        model="test-model",
    )


@pytest.mark.asyncio
async def test_openrouter_contract_and_privacy_payload() -> None:
    captured: dict[str, object] = {}

    def handler(incoming: httpx.Request) -> httpx.Response:
        captured["request"] = incoming
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "provider": "trusted-provider",
                "choices": [{"message": {"content": "answer"}}],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenRouterModelClient(
            OpenRouterConfiguration(
                api_key="not-a-real-secret",
                allowed_providers=("trusted-provider",),
            ),
            http,
        )
        result = await client.generate(request())

    incoming = captured["request"]
    assert isinstance(incoming, httpx.Request)
    payload = __import__("json").loads(incoming.content)
    assert payload["provider"] == {
        "order": ["trusted-provider"],
        "only": ["trusted-provider"],
        "allow_fallbacks": False,
        "data_collection": "deny",
        "zdr": True,
    }
    assert result.content == "answer"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [None, "unapproved-provider"])
async def test_openrouter_fails_closed_without_allowed_provider(provider: str | None) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "provider": provider,
                "choices": [{"message": {"content": "answer"}}],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenRouterModelClient(
            OpenRouterConfiguration(api_key="secret", allowed_providers=("approved",)), http
        )
        with pytest.raises(RuntimeError, match="allowed provider"):
            await client.generate(request())


def test_openrouter_configuration_cannot_disable_zdr() -> None:
    with pytest.raises(ValidationError):
        OpenRouterConfiguration(
            api_key="secret", allowed_providers=("approved",), zero_data_retention=False
        )


def test_self_hosted_configuration_rejects_public_endpoints() -> None:
    with pytest.raises(ValidationError, match="must not be public"):
        SelfHostedConfiguration(base_url="https://8.8.8.8/v1")


@pytest.mark.asyncio
async def test_self_hosted_model_client_contract() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"model": "local-model", "choices": [{"message": {"content": "local"}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = SelfHostedModelClient(SelfHostedConfiguration(), http)
        result = await client.generate(request())
    assert result.content == "local"
    assert result.provider == "self-hosted"

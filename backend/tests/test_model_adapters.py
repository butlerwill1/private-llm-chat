"""Contract and privacy tests for external and self-hosted model adapters.

HTTPX mock transports capture real outbound request objects while keeping tests
offline, deterministic and free from API usage charges.
"""

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from private_chat.adapters.openrouter import OpenRouterConfiguration, OpenRouterModelClient
from private_chat.adapters.self_hosted import SelfHostedConfiguration, SelfHostedModelClient
from private_chat.domain.models import ChatMessage, ModelRequest, Role


def request() -> ModelRequest:
    """Build the smallest realistic request shared by the adapter test cases."""

    # A ModelRequest contains the full ordered history plus the concrete model ID.
    # uuid4 and the current UTC time supply the values a real ChatMessage carries.
    return ModelRequest(
        messages=(ChatMessage(Role.USER, "private prompt", uuid4(), datetime.now(UTC)),),
        model="test-model",
    )


@pytest.mark.asyncio
async def test_openrouter_contract_and_privacy_payload() -> None:
    """OpenRouter requests must carry every configured privacy restriction.

    The response also proves that a successful provider payload is normalised
    into the vendor-neutral domain response used by the application layer.
    """

    # Arrange a mutable container so the nested HTTP handler can expose the
    # outbound request to assertions after the asynchronous client has closed.
    captured: dict[str, object] = {}

    def handler(incoming: httpx.Request) -> httpx.Response:
        """Capture the outbound request and emulate an approved provider reply."""

        captured["request"] = incoming
        # MockTransport treats this object exactly like a remote HTTP response.
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "provider": "trusted-provider",
                "choices": [{"message": {"content": "answer"}}],
            },
        )

    # MockTransport redirects every HTTP request to `handler`; no data leaves the
    # process. The context manager also closes the client after the act phase.
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        # Construct the real adapter with a fake key and one allowed provider.
        client = OpenRouterModelClient(
            OpenRouterConfiguration(
                api_key="not-a-real-secret",
                allowed_providers=("trusted-provider",),
            ),
            http,
        )
        # Act: serialise the domain request, apply privacy controls, receive the
        # fake provider response and map it back to a ModelResponse.
        result = await client.generate(request())

    # Retrieve and narrow the captured object before accessing Request fields.
    incoming = captured["request"]
    assert isinstance(incoming, httpx.Request)
    # HTTP bodies are bytes. JSON decoding converts them back to a dictionary for
    # focused assertions on the privacy-related provider section.
    payload = __import__("json").loads(incoming.content)
    # These values fail closed: only the allowlisted provider may be used, no
    # fallback may route elsewhere, collection is denied and ZDR is required.
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
    """Missing or unapproved provider attribution must invalidate a response.

    The parameterised cases cover both absent provenance and explicit routing to
    a provider outside the configured privacy allowlist.
    """

    # pytest runs this function once with None and once with an unapproved name.
    # The underscore signals that this handler does not need the request object.
    async def handler(_: httpx.Request) -> httpx.Response:
        # Return otherwise valid data so provider provenance is the only failure.
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "provider": provider,
                "choices": [{"message": {"content": "answer"}}],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        # Arrange an allowlist that contains neither parameterised response value.
        client = OpenRouterModelClient(
            OpenRouterConfiguration(api_key="secret", allowed_providers=("approved",)), http
        )
        # Act and Assert in one block: generation must raise rather than return the
        # answer. Matching text ensures the provider check caused the failure.
        with pytest.raises(RuntimeError, match="allowed provider"):
            await client.generate(request())


def test_openrouter_configuration_cannot_disable_zdr() -> None:
    """Configuration validation must prevent zero-data-retention being disabled."""

    # Pydantic validates during object construction, before any model client or
    # HTTP request exists. Passing False deliberately violates the fixed policy.
    with pytest.raises(ValidationError):
        OpenRouterConfiguration(
            api_key="secret", allowed_providers=("approved",), zero_data_retention=False
        )


def test_self_hosted_configuration_rejects_public_endpoints() -> None:
    """The private-model adapter must reject an internet-routable destination.

    A public address here could silently send sensitive prompts outside the VPC,
    so endpoint validation occurs before the client can make a request.
    """

    # 8.8.8.8 is a public address, making it an unambiguous negative example for
    # the validator that permits only loopback or private IP destinations.
    with pytest.raises(ValidationError, match="must not be public"):
        SelfHostedConfiguration(base_url="https://8.8.8.8/v1")


@pytest.mark.asyncio
async def test_self_hosted_model_client_contract() -> None:
    """An Ollama-compatible response maps to the common model response contract."""

    # Arrange an OpenAI-compatible JSON response of the kind Ollama can expose.
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"model": "local-model", "choices": [{"message": {"content": "local"}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        # The default configuration points to loopback and therefore passes the
        # private-endpoint validator without contacting a real server.
        client = SelfHostedModelClient(SelfHostedConfiguration(), http)
        # Act through the adapter's public interface.
        result = await client.generate(request())
    # Downstream business logic does not need to know the vendor response shape.
    assert result.content == "local"
    assert result.provider == "self-hosted"

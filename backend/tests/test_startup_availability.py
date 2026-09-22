import base64
from pathlib import Path

import httpx
import pytest

from private_chat.adapters.openrouter import OpenRouterConfiguration, OpenRouterModelClient
from private_chat.bootstrap import create_app
from private_chat.config import OpenRouterRoute, Settings, StorageBackend
from private_chat.domain.models import ModelRequest
from private_chat.ports.interfaces import ModelProviderError


@pytest.mark.asyncio
@pytest.mark.parametrize("catalogue_down", [False, True])
async def test_unverified_routes_do_not_stop_local_app(tmp_path: Path, catalogue_down: bool) -> None:
    def provider(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/endpoints/zdr"
        return httpx.Response(503 if catalogue_down else 200, json={"data": [
            {"model_id": "working", "tag": "approved/fp8", "provider_name": "Approved"}
        ]})

    settings = Settings(
        _env_file=None, storage_backend=StorageBackend.MEMORY,
        local_master_key_b64=base64.b64encode(b"x" * 32).decode(),
        local_data_dir=tmp_path, telemetry_enabled=False, enable_local_ollama=False,
        instructions_file=None, prompt_modes_dir=None, openrouter_api_key="test-key",
        openrouter_zdr_preflight=True, enable_openrouter=True,
        openrouter_routes=tuple(OpenRouterRoute(
            model_id=model, provider="approved", provider_name="Approved", label=model
        ) for model in ("working", "missing")),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        app = create_app(settings, http_client=http)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as browser:
                assert (await browser.get("/v1/health")).status_code == 200
                models = (await browser.get("/v1/models")).json()
                assert {m["id"]: m["available"] for m in models} == {
                    "working": not catalogue_down, "missing": False,
                }
                with pytest.raises(ValueError, match="unavailable"):
                    app.state.model_catalog.require_model("missing")

        adapter = OpenRouterModelClient(OpenRouterConfiguration(
            api_key="test-key", allowed_providers=("approved",)
        ), http)
        with pytest.raises((RuntimeError, httpx.HTTPStatusError)):
            await adapter.verify_zdr_route("missing")
        request = ModelRequest(messages=(), model="missing")
        async def emit(event: object) -> None:
            raise AssertionError("No stream event should be emitted")
        with pytest.raises(ModelProviderError, match="privacy route"):
            await adapter.generate(request)
        with pytest.raises(ModelProviderError, match="privacy route"):
            await adapter.stream(request, emit)

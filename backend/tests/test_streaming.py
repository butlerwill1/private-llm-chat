import asyncio
import base64
import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from private_chat.adapters.openrouter import OpenRouterConfiguration, OpenRouterModelClient
from private_chat.application.send_message import SendMessageCommand
from private_chat.bootstrap import create_app
from private_chat.config import ModelBackend, Settings, StorageBackend
from private_chat.domain.models import ModelRequest
from private_chat.ports.interfaces import ModelProviderError


class WireStream(httpx.AsyncByteStream):
    def __init__(self, frames: list[object], *, done: bool = True) -> None:
        self.frames = frames
        self.done = done
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        wire = (
            ": heartbeat\r\n\r\n"
            + "".join(
                "data: " + json.dumps(frame, ensure_ascii=False) + "\r\n\r\n"
                for frame in self.frames
            )
            + ("data: [DONE]\r\n\r\n" if self.done else "")
        )
        encoded = wire.encode()
        for offset in range(0, len(encoded), 7):
            yield encoded[offset : offset + 7]

    async def aclose(self) -> None:
        self.closed = True


def frame(text: str, *, provider: str | None = "Azure", finish: str | None = None) -> dict:
    return {
        "model": "test-model",
        "provider": provider,
        "choices": [{"delta": {"content": text}, "finish_reason": finish}],
    }


@pytest.mark.asyncio
async def test_stream_decodes_chunks_and_retains_privacy_controls_and_usage() -> None:
    stream = WireStream(
        [
            frame("Hello "),
            frame("世界", finish="stop"),
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                    "cost": 0.001,
                },
            },
        ]
    )

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["provider"] == {
            "order": ["azure"],
            "only": ["azure"],
            "allow_fallbacks": False,
            "data_collection": "deny",
            "zdr": True,
        }
        return httpx.Response(200, stream=stream)

    emitted: list[str] = []

    async def emit(kind: str, text: str) -> None:
        assert not stream.closed  # Text reaches the caller before the response closes.
        emitted.append(text)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        adapter = OpenRouterModelClient(
            OpenRouterConfiguration(
                api_key="test-key",
                allowed_providers=("azure",),
                allowed_provider_names=("Azure",),
            ),
            client,
        )
        result = await adapter.stream(ModelRequest((), "test-model"), emit)
    assert emitted == ["Hello ", "世界"]
    assert result.content == "Hello 世界"
    assert result.usage is not None and result.usage.total_tokens == 14
    assert stream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frames,done",
    [
        ([frame("private", provider="Unapproved")], True),
        ([frame("private", provider=None)], True),
        ([frame("partial")], False),
        ([frame("partial"), {"error": {"message": "secret upstream error"}}], True),
    ],
)
async def test_failed_streams_never_return_a_completed_response(frames: list, done: bool) -> None:
    emitted = []

    async def emit(kind: str, text: str) -> None:
        emitted.append(text)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=WireStream(frames, done=done))
        )
    ) as client:
        adapter = OpenRouterModelClient(
            OpenRouterConfiguration(
                api_key="test-key",
                allowed_providers=("azure",),
                allowed_provider_names=("Azure",),
            ),
            client,
        )
        with pytest.raises(ModelProviderError):
            await adapter.stream(ModelRequest((), "test-model"), emit)
    if frames[0].get("provider") != "Azure":
        assert emitted == []


def settings(directory: Path) -> Settings:
    return Settings(
        _env_file=None,
        model_backend=ModelBackend.SELF_HOSTED,
        model_name="test-model",
        enable_openrouter=False,
        enable_local_ollama=False,
        telemetry_enabled=False,
        local_data_dir=directory,
        instructions_file=None,
        prompt_modes_dir=None,
        storage_backend=StorageBackend.MEMORY,
        local_master_key_b64=base64.b64encode(b"x" * 32).decode(),
    )


@pytest.mark.asyncio
async def test_stream_endpoint_saves_only_completed_turns(tmp_path: Path) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=WireStream([frame("ready", finish="stop")]))
        )
    ) as inference:
        app = create_app(settings(tmp_path), http_client=inference)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as ui:
            conversation = (await ui.post("/v1/conversations")).json()
            response = await ui.post(
                f"/v1/conversations/{conversation['id']}/messages/stream", json={"content": "hello"}
            )
            events = [json.loads(line) for line in response.text.splitlines()]
            assert events[1] == {"type": "text", "text": "ready"}
            assert events[-1]["type"] == "done"
            assert [m["content"] for m in events[-1]["conversation"]["messages"]] == [
                "hello",
                "ready",
            ]


@pytest.mark.asyncio
async def test_cancelled_generation_leaves_no_turn_and_releases_busy_state(tmp_path: Path) -> None:
    from private_chat.domain.models import ModelResponse

    entered = asyncio.Event()
    released = asyncio.Event()

    class SlowModel:
        async def generate(self, request: ModelRequest) -> ModelResponse:
            return ModelResponse("ready", request.model, "test")

        async def stream(self, request: ModelRequest, emit) -> ModelResponse:
            try:
                await emit("text", "partial")
                entered.set()
                await asyncio.Event().wait()
            finally:
                released.set()
            return ModelResponse("unused", request.model, "test")

    app = create_app(settings(tmp_path), model_client=SlowModel())
    service = app.state.conversations
    view = await service.create()
    command = SendMessageCommand(view.conversation.id, "hello")

    async def emit(kind: str, text: str) -> None:
        assert (await service.get(view.conversation.id)).messages == ()

    task = asyncio.create_task(app.state.send_message.execute(command, emit))
    await asyncio.wait_for(entered.wait(), 1)
    with pytest.raises(ValueError, match="already being generated"):
        await app.state.send_message.execute(command)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert released.is_set()
    assert not (await service.get(view.conversation.id)).messages
    await app.state.send_message.execute(command)
    assert len((await service.get(view.conversation.id)).messages) == 2


@pytest.mark.asyncio
async def test_reasoning_is_status_only_and_never_returned_as_answer() -> None:
    events = []

    async def emit(kind: str, text: str) -> None:
        events.append((kind, text))

    frames = [
        {"provider": "Azure", "choices": [{"delta": {"reasoning": "private reasoning"}}]},
        frame("Answer", finish="stop"),
    ]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=WireStream(frames)))
    ) as client:
        adapter = OpenRouterModelClient(
            OpenRouterConfiguration(
                api_key="test", allowed_providers=("azure",), allowed_provider_names=("Azure",)
            ), client
        )
        result = await adapter.stream(ModelRequest((), "test-model"), emit)
    assert events == [("status", "Thinking…"), ("text", "Answer")]
    assert result.content == "Answer"


@pytest.mark.asyncio
async def test_endpoint_sanitizes_upstream_failures_and_does_not_save(tmp_path: Path) -> None:
    frames = [frame("Partial"), {"error": {"message": "private upstream error body"}}]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=WireStream(frames)))
    ) as inference:
        app = create_app(settings(tmp_path), http_client=inference)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as ui:
            conversation = (await ui.post("/v1/conversations")).json()
            url = f"/v1/conversations/{conversation['id']}"
            response = await ui.post(url + "/messages/stream", json={"content": "hello"})
            events = [json.loads(line) for line in response.text.splitlines()]
            assert events[-1]["type"] == "error"
            assert "private upstream error body" not in response.text
            assert (await ui.get(url)).json()["messages"] == []

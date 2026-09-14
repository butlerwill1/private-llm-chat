import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from time import perf_counter
from typing import Annotated, cast
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from private_chat.adapters.telemetry import LocalSystemMonitor, TelemetryStore
from private_chat.api.schemas import (
    ChangeModelRequest,
    ConversationResponse,
    ConversationSummaryResponse,
    CreateConversationRequest,
    HealthResponse,
    ModelConfigurationResponse,
    ModelOptionResponse,
    RenameConversationRequest,
    SendMessageRequest,
    SystemMonitorResponse,
    TelemetryStatusResponse,
)
from private_chat.application.conversations import ConversationService
from private_chat.application.model_router import ConfiguredModelCatalog, ModelOption
from private_chat.application.send_message import SendMessage, SendMessageCommand
from private_chat.ports.interfaces import ModelProviderError

router = APIRouter()


def get_send_message(request: Request) -> SendMessage:
    return cast(SendMessage, request.app.state.send_message)


def get_conversations(request: Request) -> ConversationService:
    return cast(ConversationService, request.app.state.conversations)


def get_model_options(request: Request) -> tuple[ModelOption, ...]:
    return cast(tuple[ModelOption, ...], request.app.state.model_options)


def get_model_catalog(request: Request) -> ConfiguredModelCatalog:
    return cast(ConfiguredModelCatalog, request.app.state.model_catalog)


def get_custom_model_allowed(request: Request) -> bool:
    return cast(bool, request.app.state.custom_openrouter_model_allowed)


def get_model_backend(request: Request) -> str:
    return cast(str, request.app.state.model_backend)


def get_storage_label(request: Request) -> str:
    return cast(str, request.app.state.storage_label)


def get_system_monitor(request: Request) -> LocalSystemMonitor:
    return cast(LocalSystemMonitor, request.app.state.system_monitor)


def get_telemetry_store(request: Request) -> TelemetryStore:
    return cast(TelemetryStore, request.app.state.telemetry_store)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/system-monitor", response_model=SystemMonitorResponse)
async def system_monitor(
    monitor: Annotated[LocalSystemMonitor, Depends(get_system_monitor)],
    store: Annotated[TelemetryStore, Depends(get_telemetry_store)],
) -> SystemMonitorResponse:
    """Return operational local hardware data only; never transcript data."""
    snapshot = await monitor.snapshot()
    count, database_bytes = store.status()
    return SystemMonitorResponse(
        snapshot=snapshot,
        telemetry=TelemetryStatusResponse(sample_count=count, database_bytes=database_bytes),
    )


@router.get("/system-monitor/export")
async def export_system_monitor(
    store: Annotated[TelemetryStore, Depends(get_telemetry_store)],
) -> Response:
    return Response(
        store.export_json(),
        media_type="application/json",
        headers={
            "Content-Disposition": "attachment; filename=private-chat-performance-telemetry.json"
        },
    )


@router.get("/models", response_model=tuple[ModelOptionResponse, ...])
async def list_models(
    options: Annotated[tuple[ModelOption, ...], Depends(get_model_options)],
) -> tuple[ModelOptionResponse, ...]:
    """Return only the approved model catalogue for this local session."""

    return tuple(
        ModelOptionResponse(
            id=item.id,
            label=item.label,
            backend=item.backend,
            provider=item.provider,
            available=item.available,
        )
        for item in options
    )


@router.get("/model-configuration", response_model=ModelConfigurationResponse)
async def model_configuration(
    request: Request,
    custom_model_allowed: Annotated[bool, Depends(get_custom_model_allowed)],
    model_backend: Annotated[str, Depends(get_model_backend)],
    storage_label: Annotated[str, Depends(get_storage_label)],
) -> ModelConfigurationResponse:
    """Tell the browser whether typed OpenRouter model IDs are enabled locally."""

    return ModelConfigurationResponse(
        custom_openrouter_model_allowed=custom_model_allowed,
        model_backend=model_backend,
        storage_label=storage_label,
        prompt_modes=request.app.state.prompt_modes,
    )


@router.get("/conversations", response_model=tuple[ConversationResponse, ...])
async def list_conversations(
    service: Annotated[ConversationService, Depends(get_conversations)],
    catalog: Annotated[ConfiguredModelCatalog, Depends(get_model_catalog)],
) -> tuple[ConversationResponse, ...]:
    views = await service.list()
    return tuple(ConversationResponse.from_view(view, catalog) for view in views)


@router.get("/conversation-summaries", response_model=tuple[ConversationSummaryResponse, ...])
async def list_conversation_summaries(
    service: Annotated[ConversationService, Depends(get_conversations)],
) -> tuple[ConversationSummaryResponse, ...]:
    """Return navigation metadata without loading encrypted message content."""

    return tuple(
        ConversationSummaryResponse.from_domain(conversation)
        for conversation in await service.list_metadata()
    )


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    service: Annotated[ConversationService, Depends(get_conversations)],
    catalog: Annotated[ConfiguredModelCatalog, Depends(get_model_catalog)],
    body: CreateConversationRequest | None = None,
) -> ConversationResponse:
    try:
        return ConversationResponse.from_view(
            await service.create(None if body is None else body.model_id), catalog
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    service: Annotated[ConversationService, Depends(get_conversations)],
    catalog: Annotated[ConfiguredModelCatalog, Depends(get_model_catalog)],
) -> ConversationResponse:
    view = await service.get(conversation_id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return ConversationResponse.from_view(view, catalog)


@router.patch("/conversations/{conversation_id}/model", response_model=ConversationResponse)
async def change_model(
    conversation_id: UUID,
    body: ChangeModelRequest,
    service: Annotated[ConversationService, Depends(get_conversations)],
    catalog: Annotated[ConfiguredModelCatalog, Depends(get_model_catalog)],
) -> ConversationResponse:
    try:
        return ConversationResponse.from_view(
            await service.change_model(conversation_id, body.model_id), catalog
        )
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


@router.patch("/conversations/{conversation_id}/title", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: UUID,
    body: RenameConversationRequest,
    service: Annotated[ConversationService, Depends(get_conversations)],
    catalog: Annotated[ConfiguredModelCatalog, Depends(get_model_catalog)],
) -> ConversationResponse:
    try:
        return ConversationResponse.from_view(
            await service.rename(conversation_id, body.title), catalog
        )
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    service: Annotated[ConversationService, Depends(get_conversations)],
) -> Response:
    if not await service.delete(conversation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/conversations/{conversation_id}/messages", response_model=ConversationResponse)
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    use_case: Annotated[SendMessage, Depends(get_send_message)],
    service: Annotated[ConversationService, Depends(get_conversations)],
    catalog: Annotated[ConfiguredModelCatalog, Depends(get_model_catalog)],
    telemetry: Annotated[TelemetryStore, Depends(get_telemetry_store)],
) -> ConversationResponse:
    # Never log `body`: it contains plaintext user content.
    try:
        started_at = perf_counter()
        await use_case.execute(
            SendMessageCommand(
                conversation_id=conversation_id,
                content=body.content,
                prompt_mode_id=body.prompt_mode_id,
            )
        )
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except httpx.TimeoutException as error:
        # A local model can need time to generate, but a finite timeout still
        # protects the browser from a permanently broken tunnel or model service.
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The local model did not respond before the inference timeout.",
        ) from error
    except ModelProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The selected model provider returned an unusable response. Please try again.",
        ) from error
    view = await service.get(conversation_id)
    if view is None:
        raise RuntimeError("Conversation disappeared after a completed turn")
    response = ConversationResponse.from_view(view, catalog)
    assistant = next(
        (message for message in reversed(response.messages) if message.role.value == "assistant"),
        None,
    )
    if (
        assistant is not None
        and assistant.usage is not None
        and assistant.usage.provider == "self-hosted"
    ):
        telemetry.record_inference(
            {
                "model": assistant.usage.model,
                "duration_ms": round((perf_counter() - started_at) * 1000),
                "input_tokens": assistant.usage.input_tokens,
                "output_tokens": assistant.usage.output_tokens,
                "total_tokens": assistant.usage.total_tokens,
                "outcome": "success",
            }
        )
    return response


@router.post("/conversations/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    request: Request,
    use_case: Annotated[SendMessage, Depends(get_send_message)],
    service: Annotated[ConversationService, Depends(get_conversations)],
    catalog: Annotated[ConfiguredModelCatalog, Depends(get_model_catalog)],
    telemetry: Annotated[TelemetryStore, Depends(get_telemetry_store)],
) -> StreamingResponse:
    if await service.get(conversation_id) is None:
        raise HTTPException(404, "Conversation not found")

    async def events() -> AsyncIterator[str]:
        # Bounded buffering applies backpressure; disconnect cancels the provider request.
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=32)

        async def emit(kind: str, text: str) -> None:
            await queue.put({"type": kind, "text": text})

        async def produce() -> None:
            started = perf_counter()
            try:
                assistant = await use_case.execute(
                    SendMessageCommand(conversation_id, body.content, body.prompt_mode_id), emit
                )
                view = await service.get(conversation_id)
                if view is None:
                    raise RuntimeError("Conversation disappeared")
                result = ConversationResponse.from_view(view, catalog)
                usage = assistant.usage
                if usage is not None and usage.provider == "self-hosted":
                    # Telemetry must never convert an already saved turn into a failed stream.
                    with suppress(Exception):
                        telemetry.record_inference({
                            "model": usage.model,
                            "duration_ms": round((perf_counter() - started) * 1000),
                            "input_tokens": usage.input_tokens,
                            "output_tokens": usage.output_tokens,
                            "total_tokens": usage.total_tokens,
                            "outcome": "success",
                        })
                await queue.put({"type": "done", "conversation": result.model_dump(mode="json")})
            except asyncio.CancelledError:
                raise
            except Exception:
                # Never expose upstream bodies, prompts or secrets in an error event.
                await queue.put({
                    "type": "error",
                    "text": "Response interrupted. The answer may be incomplete; "
                    "reload the conversation to check whether it was saved.",
                })

        task = asyncio.create_task(produce())
        try:
            yield json.dumps({"type": "status", "text": "Waiting for the model…"}) + "\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield json.dumps({"type": "heartbeat"}) + "\n"
                    continue
                yield json.dumps(event, ensure_ascii=False) + "\n"
                if event["type"] in {"done", "error"}:
                    break
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(
        events(), media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )

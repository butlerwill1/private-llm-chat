"""Incremental SSE decoding shared by OpenAI-compatible model endpoints."""

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

from private_chat.domain.models import ModelResponse, TurnUsage
from private_chat.ports.interfaces import ModelProviderError, StreamCallback


async def sse_data(response: httpx.Response) -> AsyncIterator[str]:
    lines: list[str] = []
    async for line in response.aiter_lines():
        if not line:
            if lines:
                yield "\n".join(lines)
                lines.clear()
        elif line.startswith("data:"):
            lines.append(line[5:].removeprefix(" "))
        # Comments, event IDs and keep-alives contain no completion data.
    if lines:
        yield "\n".join(lines)


async def stream_completion(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    emit: StreamCallback,
    *,
    provider: str,
    parse_usage: Callable[..., TurnUsage | None],
    allowed_provider_names: tuple[str, ...] | None = None,
) -> ModelResponse:
    pieces: list[str] = []
    model = str(payload["model"])
    usage = None
    confirmed = allowed_provider_names is None
    finished = False
    done = False
    thinking = False
    async with client.stream(
        "POST",
        url,
        headers=headers,
        json={**payload, "stream": True, "stream_options": {"include_usage": True}},
    ) as response:
        response.raise_for_status()
        async for data in sse_data(response):
            if data == "[DONE]":
                done = True
                break
            try:
                frame = json.loads(data)
            except ValueError as exc:
                raise ModelProviderError("Invalid model stream") from exc
            if not isinstance(frame, dict) or frame.get("error"):
                raise ModelProviderError("Model stream failed")
            reported_provider = frame.get("provider")
            if allowed_provider_names is not None and reported_provider is not None:
                if reported_provider not in allowed_provider_names:
                    raise ModelProviderError("Model stream used an unapproved provider")
                provider = reported_provider
                confirmed = True
            if isinstance(frame.get("model"), str):
                model = frame["model"]
            if frame.get("usage") is not None:
                usage = parse_usage(frame["usage"], model=model, provider=provider)
            choices = frame.get("choices", [])
            if not isinstance(choices, list):
                raise ModelProviderError("Invalid stream choices")
            for choice in choices:
                if not isinstance(choice, dict):
                    raise ModelProviderError("Invalid stream choice")
                finish = choice.get("finish_reason")
                if finish == "error":
                    raise ModelProviderError("Model stream failed")
                finished = finished or finish is not None
                delta = choice.get("delta") or {}
                if not isinstance(delta, dict):
                    raise ModelProviderError("Invalid stream delta")
                content = delta.get("content")
                reasoning = (
                    delta.get("reasoning")
                    or delta.get("reasoning_content")
                    or delta.get("reasoning_details")
                )
                if (content or reasoning) and not confirmed:
                    raise ModelProviderError("Stream did not confirm an approved provider")
                if reasoning and not thinking:
                    thinking = True
                    await emit("status", "Thinking…")
                if content is not None:
                    if not isinstance(content, str):
                        raise ModelProviderError("Invalid streamed text")
                    if content:
                        pieces.append(content)
                        await emit("text", content)
    content = "".join(pieces)
    if not done or not finished or not confirmed or not content.strip():
        raise ModelProviderError("The model stream ended before a complete answer")
    return ModelResponse(content, model, provider, usage)

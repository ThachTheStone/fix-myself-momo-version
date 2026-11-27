from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.llm.router import LLMResponse, ModelTarget


class FakeLLM:
    """Model giả trả kịch bản tool call hoặc text cố định cho unit test."""

    def __init__(
        self,
        responses: list[LLMResponse | Exception] | None = None,
        handler: Callable[[list[dict[str, Any]], list[dict[str, Any]], ModelTarget], LLMResponse]
        | None = None,
    ) -> None:
        self._queue: list[LLMResponse | Exception] = list(responses or [])
        self._handler = handler
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        target: ModelTarget,
        timeout_s: float,
        max_tokens: int,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "target": target,
                "timeout_s": timeout_s,
                "max_tokens": max_tokens,
            }
        )
        if self._handler is not None:
            return self._handler(messages, tools, target)
        if not self._queue:
            return LLMResponse(content="Xong.", tool_calls=[], model_target=target)
        nxt = self._queue.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return LLMResponse(
            content=nxt.content,
            tool_calls=nxt.tool_calls,
            model_target=target,
        )

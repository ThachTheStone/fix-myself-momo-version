from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx
import truststore

truststore.inject_into_ssl()
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
import litellm  # noqa: E402

from app.config import Settings  # noqa: E402

ModelTarget = Literal["small", "cloud", "cloud_backup"]
TaskKind = Literal["chat", "document", "batch", "morning_plan", "datagen"]


@dataclass
class ToolCallSpec:
    """Thông tin một tool call trả về từ model."""

    id: str
    name: str
    arguments: str | dict[str, Any]


@dataclass
class LLMResponse:
    """Kết quả chuẩn hoá từ LLM."""

    content: str = ""
    tool_calls: list[ToolCallSpec] = field(default_factory=list)
    model_target: ModelTarget = "small"


@dataclass
class RouterError(Exception):
    """Lỗi định tuyến model (CLOUD_DISABLED, MODEL_UNAVAILABLE)."""

    code: str
    message: str


class LLMClientProtocol(Protocol):
    """Giao diện gọi model để thay bằng FakeLLM trong unit test."""

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        target: ModelTarget,
        timeout_s: float,
        max_tokens: int,
    ) -> LLMResponse: ...


class LiteLLMClient:
    """Gọi model thật qua LiteLLM tới Ollama (OpenAI-compatible) hoặc cloud."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        target: ModelTarget,
        timeout_s: float,
        max_tokens: int,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "messages": messages,
            "tools": tools or None,
            "temperature": 0,
            "timeout": timeout_s,
            "max_tokens": max_tokens,
            "num_retries": 0,
            "max_retries": 0,
        }

        if target == "small":
            is_qwen3 = "qwen3" in self._settings.small_model_name.lower()
            if is_qwen3:
                # Qwen3 qua /v1/chat/completions chỉ tắt thinking khi cuối user message có /no_think
                patched_messages = [dict(m) for m in messages]
                for idx in range(len(patched_messages) - 1, -1, -1):
                    if patched_messages[idx].get("role") == "user":
                        content = str(patched_messages[idx].get("content") or "")
                        if not content.rstrip().endswith("/no_think"):
                            patched_messages[idx]["content"] = f"{content} /no_think"
                        break
                kwargs["messages"] = patched_messages
                kwargs["extra_body"] = {"think": False}
            else:
                kwargs["messages"] = messages
            kwargs["model"] = f"openai/{self._settings.small_model_name}"
            kwargs["api_base"] = self._settings.small_model_base_url
            kwargs["api_key"] = "ollama"
        elif target == "cloud":
            if not self._settings.cloud_model or not self._settings.cloud_api_key:
                raise RouterError("CLOUD_NOT_CONFIGURED", "Chưa cấu hình model cloud")
            kwargs["model"] = self._settings.cloud_model
            kwargs["api_key"] = self._settings.cloud_api_key
        else:
            if not self._settings.cloud_backup_model or not self._settings.cloud_backup_api_key:
                raise RouterError("CLOUD_NOT_CONFIGURED", "Chưa cấu hình model cloud_backup")
            kwargs["model"] = self._settings.cloud_backup_model
            kwargs["api_key"] = self._settings.cloud_backup_api_key

        resp = await litellm.acompletion(**kwargs)
        choice = resp.choices[0]
        message = choice.message
        content = getattr(message, "content", None) or ""
        raw_calls = getattr(message, "tool_calls", None) or []

        parsed_calls: list[ToolCallSpec] = []
        for idx, tc in enumerate(raw_calls):
            fn = getattr(tc, "function", None)
            if fn is None and isinstance(tc, dict):
                fn = tc.get("function", {})
                tc_id = str(tc.get("id") or f"call_{idx}")
                name = str(fn.get("name", ""))
                arguments = fn.get("arguments", "{}")
            else:
                tc_id = str(getattr(tc, "id", None) or f"call_{idx}")
                name = str(getattr(fn, "name", ""))
                arguments = getattr(fn, "arguments", "{}")
            parsed_calls.append(ToolCallSpec(id=tc_id, name=name, arguments=arguments))

        return LLMResponse(content=content, tool_calls=parsed_calls, model_target=target)


class SmallHealthState:
    """Theo dõi trạng thái sống/chết của model nhỏ (QĐ-HARNESS-007)."""

    def __init__(self) -> None:
        self.small_down: bool = False
        self._consecutive_failures: int = 0
        self._consecutive_successes: int = 0

    def record_failure(self) -> None:
        self._consecutive_successes = 0
        self._consecutive_failures += 1
        if self._consecutive_failures >= 2:
            self.small_down = True

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._consecutive_successes += 1
        if self._consecutive_successes >= 3:
            self.small_down = False

    async def probe(self, http_client: httpx.AsyncClient, base_url: str) -> bool:
        """Gọi GET /models trên endpoint small để cập nhật trạng thái."""
        try:
            resp = await http_client.get(f"{base_url.rstrip('/')}/models", timeout=3.0)
            if resp.status_code < 400:
                self.record_success()
                return True
        except Exception:
            pass
        self.record_failure()
        return False


class ModelRouter:
    """Định tuyến small -> cloud -> cloud_backup (QĐ-HARNESS-007, [INV-HARNESS-10])."""

    def __init__(
        self,
        settings: Settings,
        client: LLMClientProtocol | None = None,
        health: SmallHealthState | None = None,
    ) -> None:
        self._settings = settings
        self._client: LLMClientProtocol = client or LiteLLMClient(settings)
        self.health = health or SmallHealthState()
        self._semaphore = asyncio.Semaphore(max(1, settings.small_max_concurrency))
        self.last_target: ModelTarget = "small"

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        task_kind: TaskKind = "chat",
        force_cloud: bool = False,
    ) -> LLMResponse:
        mode = self._settings.router_mode
        needs_cloud = force_cloud or task_kind != "chat"

        if mode == "small_only":
            if needs_cloud:
                raise RouterError(
                    "CLOUD_DISABLED",
                    "Tác vụ cần model cloud nhưng ROUTER_MODE đang đặt là small_only",
                )
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=0.001)
            except TimeoutError as exc:
                raise RouterError(
                    "MODEL_UNAVAILABLE",
                    "Trợ lý đang bận, thử lại sau 1 phút",
                ) from exc
            try:
                resp = await self._client.complete(
                    messages,
                    tools,
                    target="small",
                    timeout_s=self._settings.small_timeout_s,
                    max_tokens=self._settings.max_response_tokens,
                )
                self.last_target = "small"
                return resp
            except Exception as exc:
                raise RouterError(
                    "MODEL_UNAVAILABLE",
                    "Trợ lý đang bận, thử lại sau 1 phút",
                ) from exc
            finally:
                self._semaphore.release()

        if mode == "hybrid" and not needs_cloud and not self.health.small_down:
            acquired = False
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=0.001)
                acquired = True
            except TimeoutError:
                acquired = False

            if acquired:
                try:
                    resp = await self._client.complete(
                        messages,
                        tools,
                        target="small",
                        timeout_s=self._settings.small_timeout_s,
                        max_tokens=self._settings.max_response_tokens,
                    )
                    self.last_target = "small"
                    return resp
                except Exception:
                    pass
                finally:
                    self._semaphore.release()

        # Fallback sang cloud -> cloud_backup ([INV-HARNESS-10])
        for target in ("cloud", "cloud_backup"):
            try:
                resp = await self._client.complete(
                    messages,
                    tools,
                    target=target,
                    timeout_s=self._settings.cloud_timeout_s,
                    max_tokens=self._settings.max_response_tokens,
                )
                self.last_target = target
                return resp
            except Exception:
                continue

        raise RouterError("MODEL_UNAVAILABLE", "Trợ lý đang bận, thử lại sau 1 phút")

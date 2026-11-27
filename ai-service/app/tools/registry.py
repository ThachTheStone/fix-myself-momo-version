from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from app.policy.permission import Risk
from app.tools.be_client import BEClient, BEResponse

RunsOn = Literal["server", "client", "server_client"]


@dataclass
class ToolContext:
    """Ngữ cảnh thực thi một tool trong lượt chat."""

    user_id: str
    jwt: str
    turn_id: str
    be: BEClient
    last_write_turn_id: str | None = None


@dataclass
class Tool:
    """Định nghĩa một tool trong danh mục (QĐ-HARNESS-001)."""

    name: str
    description: str
    args_model: type[BaseModel]
    risk: Risk
    runs_on: RunsOn
    call: Callable[[BaseModel, ToolContext], Awaitable[BEResponse]]
    summarize: Callable[[BEResponse], str]

    def openai_schema(self) -> dict[str, Any]:
        """Xuất JSON schema theo chuẩn OpenAI function calling cho LiteLLM."""
        raw_schema = self.args_model.model_json_schema(by_alias=True)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": raw_schema,
            },
        }


class ToolRegistry:
    """Kho đăng ký các tool hợp lệ của AI Harness."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[dict[str, Any]]:
        return [tool.openai_schema() for tool in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())

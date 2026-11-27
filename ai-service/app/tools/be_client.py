from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel


@dataclass
class BEError(Exception):
    """Lỗi trả về từ Backend REST API."""

    status_code: int
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code} ({self.status_code}): {self.message}"


@dataclass
class BEResponse:
    """Kết quả chuẩn hoá trả về từ BE."""

    data: Any
    action_id: str | None = None


def compute_idempotency_key(turn_id: str, tool_name: str, args: BaseModel) -> str:
    """Sinh Idempotency-Key từ turnId + tool + args chuẩn hoá (QĐ-HARNESS-015, [INV-HARNESS-09])."""
    payload_dict = args.model_dump(mode="json", by_alias=True, exclude_none=True)
    raw = f"{turn_id}{tool_name}{json.dumps(payload_dict, sort_keys=True, ensure_ascii=False)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class BEClient:
    """HTTP client gọi REST Backend bằng JWT của người dùng (QĐ-HARNESS-003, [INV-HARNESS-04])."""

    def __init__(
        self, http_client: httpx.AsyncClient, base_url: str, timeout_s: float = 10.0
    ) -> None:
        self._client = http_client
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    async def request(
        self,
        method: str,
        path: str,
        *,
        jwt: str,
        turn_id: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> BEResponse:
        """Gửi request tới BE; không ghi log JWT hay dữ liệu nhạy cảm."""
        headers: dict[str, str] = {
            "Authorization": f"Bearer {jwt}",
            "X-Turn-Id": turn_id,
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        url = f"{self._base_url}{path}"
        resp = await self._client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            timeout=self._timeout_s,
        )

        if resp.status_code == 401:
            raise BEError(401, "UNAUTHORIZED", "Phiên đăng nhập đã hết hạn")

        if resp.status_code >= 400:
            code = resp.headers.get("x-error-code", "BE_ERROR")
            message = resp.text
            try:
                err_json = resp.json()
                if isinstance(err_json, dict):
                    code = str(err_json.get("code") or code)
                    message = str(err_json.get("message") or message)
            except ValueError:
                pass
            raise BEError(resp.status_code, code, message)

        if resp.status_code == 204 or not resp.content:
            return BEResponse(data=None, action_id=None)

        body = resp.json()
        if isinstance(body, dict) and "data" in body:
            return BEResponse(data=body.get("data"), action_id=body.get("actionId"))
        return BEResponse(data=body, action_id=None)

    async def get(
        self,
        path: str,
        *,
        jwt: str,
        turn_id: str,
        params: dict[str, Any] | None = None,
    ) -> BEResponse:
        return await self.request("GET", path, jwt=jwt, turn_id=turn_id, params=params)

    async def post(
        self,
        path: str,
        args: BaseModel,
        *,
        jwt: str,
        turn_id: str,
        tool_name: str,
        write: bool = True,
    ) -> BEResponse:
        idem_key = compute_idempotency_key(turn_id, tool_name, args) if write else None
        payload = args.model_dump(mode="json", by_alias=True, exclude_none=True)
        return await self.request(
            "POST",
            path,
            jwt=jwt,
            turn_id=turn_id,
            json_body=payload,
            idempotency_key=idem_key,
        )

    async def patch(
        self,
        path: str,
        payload: dict[str, Any],
        args: BaseModel,
        *,
        jwt: str,
        turn_id: str,
        tool_name: str,
    ) -> BEResponse:
        idem_key = compute_idempotency_key(turn_id, tool_name, args)
        return await self.request(
            "PATCH",
            path,
            jwt=jwt,
            turn_id=turn_id,
            json_body=payload,
            idempotency_key=idem_key,
        )

    async def delete(
        self,
        path: str,
        args: BaseModel,
        *,
        jwt: str,
        turn_id: str,
        tool_name: str,
    ) -> BEResponse:
        idem_key = compute_idempotency_key(turn_id, tool_name, args)
        return await self.request(
            "DELETE",
            path,
            jwt=jwt,
            turn_id=turn_id,
            idempotency_key=idem_key,
        )

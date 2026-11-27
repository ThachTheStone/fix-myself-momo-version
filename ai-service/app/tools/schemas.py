from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationInfo, field_validator

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _attach_default_tz(value: Any) -> Any:
    """Gắn offset +07:00 nếu datetime thiếu múi giờ (QĐ-HARNESS-009, [INV-HARNESS-11])."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        dt = datetime.fromisoformat(stripped)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=VN_TZ)
        return dt
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=VN_TZ)
    return value


class ListTasksArgs(BaseModel):
    """Tham số liệt kê task theo bộ lọc."""

    status: Literal["todo", "in_progress", "done"] | None = None
    priority: int | None = Field(default=None, ge=1, le=4)
    dueFrom: AwareDatetime | None = None
    dueTo: AwareDatetime | None = None
    parentId: UUID | None = None
    limit: int = Field(default=50, ge=1, le=50)

    @field_validator("dueFrom", "dueTo", mode="before")
    @classmethod
    def _normalize_dt(cls, value: Any) -> Any:
        return _attach_default_tz(value)


class SearchTasksArgs(BaseModel):
    """Tham số tìm kiếm task theo từ khoá tiêu đề."""

    query: str = Field(min_length=1, max_length=200)


class GetTaskArgs(BaseModel):
    """Tham số lấy chi tiết một task."""

    taskId: str = Field(min_length=1, max_length=64)


class GetScheduleArgs(BaseModel):
    """Tham số xem lịch trong khoảng thời gian."""

    model_config = ConfigDict(populate_by_name=True)

    from_: AwareDatetime = Field(alias="from")
    to: AwareDatetime

    @field_validator("from_", "to", mode="before")
    @classmethod
    def _normalize_dt(cls, value: Any) -> Any:
        return _attach_default_tz(value)


class CreateTaskArgs(BaseModel):
    """Tham số tạo một task mới (QĐ-HARNESS-009, [INV-HARNESS-07], [INV-HARNESS-11])."""

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    deadline: AwareDatetime | None = None
    priority: int = Field(default=3, ge=1, le=4)
    parentId: UUID | None = None
    estimateMin: int | None = Field(default=None, ge=5, le=2400)

    @field_validator("deadline", mode="before")
    @classmethod
    def _normalize_deadline(cls, value: Any) -> Any:
        return _attach_default_tz(value)

    @field_validator("deadline", mode="after")
    @classmethod
    def _validate_not_in_past(
        cls, value: AwareDatetime | None, info: ValidationInfo
    ) -> AwareDatetime | None:
        return _check_not_past(value, info)


def _check_not_past(value: AwareDatetime | None, info: ValidationInfo) -> AwareDatetime | None:
    if value is None:
        return None
    now: datetime | None = None
    if isinstance(info.context, dict):
        now = info.context.get("now")
    if now is None:
        now = datetime.now(VN_TZ)
    if value < now - timedelta(minutes=5):
        raise ValueError("thời gian đã qua")
    return value


class UpdateTaskArgs(BaseModel):
    """Tham số cập nhật một task (QĐ-HARNESS-009, [INV-HARNESS-07])."""

    taskId: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    deadline: AwareDatetime | None = None
    priority: int | None = Field(default=None, ge=1, le=4)
    estimateMin: int | None = Field(default=None, ge=5, le=2400)
    status: Literal["todo", "in_progress", "done"] | None = None

    @field_validator("deadline", mode="before")
    @classmethod
    def _normalize_deadline(cls, value: Any) -> Any:
        return _attach_default_tz(value)

    @field_validator("deadline", mode="after")
    @classmethod
    def _validate_not_in_past(
        cls, value: AwareDatetime | None, info: ValidationInfo
    ) -> AwareDatetime | None:
        return _check_not_past(value, info)


class SetPriorityArgs(BaseModel):
    """Tham số đổi mức ưu tiên cho một task."""

    taskId: str = Field(min_length=1, max_length=64)
    priority: int = Field(ge=1, le=4)
    reason: str = Field(default="", max_length=500)


class CompleteTaskArgs(BaseModel):
    """Tham số đánh dấu hoàn thành một task."""

    taskId: str = Field(min_length=1, max_length=64)


class DeleteTaskArgs(BaseModel):
    """Tham số xoá mềm một task (luôn qua pending_action, [INV-HARNESS-02])."""

    taskId: str = Field(min_length=1, max_length=64)


class ReprioritizeItem(BaseModel):
    """Một mục trong thao tác đổi ưu tiên hàng loạt."""

    taskId: str = Field(min_length=1, max_length=64)
    priority: int = Field(ge=1, le=4)


class ReprioritizeTasksArgs(BaseModel):
    """Tham số đổi ưu tiên nhiều task trong một lô."""

    items: list[ReprioritizeItem] = Field(min_length=1, max_length=50)
    reason: str = Field(default="", max_length=500)


class CreateReminderArgs(BaseModel):
    """Tham số tạo nhắc nhở kèm thông báo trên máy (QĐ-HARNESS-009, [INV-HARNESS-11])."""

    remindAt: AwareDatetime
    message: str = Field(min_length=1, max_length=200)
    taskId: str | None = Field(default=None, max_length=64)

    @field_validator("remindAt", mode="before")
    @classmethod
    def _normalize_remind_at(cls, value: Any) -> Any:
        return _attach_default_tz(value)

    @field_validator("remindAt", mode="after")
    @classmethod
    def _validate_not_in_past(cls, value: AwareDatetime, info: ValidationInfo) -> AwareDatetime:
        checked = _check_not_past(value, info)
        assert checked is not None
        return checked


class UndoLastActionArgs(BaseModel):
    """Tham số hoàn tác lượt thao tác gần nhất (QĐ-HARNESS-006)."""

    pass

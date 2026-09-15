from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChatCreateRequest(BaseModel):
    title: str = "新会话"


class ChatCreateResponse(BaseModel):
    conversation_id: int
    title: str
    status: str


class ChatDeleteRequest(BaseModel):
    conversation_ids: list[int]


class ChatUpdateRequest(BaseModel):
    conversation_id: int
    title: str


class ConversationItem(BaseModel):
    conversation_id: int
    title: str
    status: str
    last_message_at: datetime | None = None


class AttachmentBrief(BaseModel):
    attachment_id: int
    file_name: str
    file_type: str
    file_size: int
    parse_status: str
    created_at: datetime


class MessageItem(BaseModel):
    message_id: int
    role: str
    content: str
    attachments: list[AttachmentBrief] = Field(default_factory=list)
    created_at: datetime


class AttachmentUploadResponse(BaseModel):
    attachment_id: int
    file_name: str
    file_path: str


class AttachmentDeleteRequest(BaseModel):
    attachment_id: int


class WsTokenResponse(BaseModel):
    websocket_token: str
    expires_in: int


class WsTokenRequest(BaseModel):
    conversation_id: int


class ChatSendRequest(BaseModel):
    conversation_id: int
    content: str


class ChatSendResponse(BaseModel):
    task_id: int
    message_id: int
    task_status: str


class TaskStatusResponse(BaseModel):
    task_status: str
    current_step: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None


class KeyMetric(BaseModel):
    metric_name: str
    metric_value: Any
    metric_unit: str = ""
    metric_period: str = ""


class EvidenceItem(BaseModel):
    source_type: str
    source_name: str
    evidence_text: str
    related_metric: str = ""
    confidence: float = 0.8


class ResultResponse(BaseModel):
    problem_definition: str
    key_metrics: list[KeyMetric]
    evidence_list: list[EvidenceItem]
    conclusion_text: str
    missing_data_text: str
    next_action_text: str
    result_markdown: str = ""
    result_file_path: str | None = None
    result_id: int | None = None


class ReloadResponse(BaseModel):
    status: str
    message: str


class CancelTaskRequest(BaseModel):
    task_id: int

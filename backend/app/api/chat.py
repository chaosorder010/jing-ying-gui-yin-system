from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import AnalysisTask, User
from app.schemas import (
    ChatCreateRequest,
    ChatCreateResponse,
    ChatDeleteRequest,
    ChatSendRequest,
    ChatSendResponse,
    ChatUpdateRequest,
    ConversationItem,
    MessageItem,
    AttachmentBrief,
    WsTokenRequest,
    WsTokenResponse,
)
from app.services import chat as chat_service
from app.services.attachment import list_attachments
from app.services.config_service import issue_ws_token

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/create", response_model=ChatCreateResponse)
def create_chat(
    body: ChatCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = chat_service.create_conversation(db, user.id, body.title)
    return ChatCreateResponse(conversation_id=conv.id, title=conv.title, status=conv.status)


@router.post("/delete")
def delete_chat(
    body: ChatDeleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = chat_service.soft_delete_conversations(db, user.id, body.conversation_ids)
    return {"deleted": count}


@router.post("/update")
def update_chat(
    body: ChatUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = chat_service.get_conversation_for_user(db, user.id, body.conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    conv = chat_service.update_conversation_title(db, conv, body.title)
    return {"conversation_id": conv.id, "title": conv.title, "status": conv.status}


@router.get("/ls", response_model=list[ConversationItem])
def list_chats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = chat_service.list_conversations(db, user.id)
    return [
        ConversationItem(
            conversation_id=c.id,
            title=c.title,
            status=c.status,
            last_message_at=c.last_message_at,
        )
        for c in items
    ]


@router.get("/ls/{conversation_id}", response_model=list[MessageItem])
def list_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = chat_service.get_conversation_for_user(db, user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = chat_service.list_messages(db, conversation_id)
    atts = list_attachments(db, conversation_id)
    att_by_msg: dict[int | None, list] = {}
    for a in atts:
        att_by_msg.setdefault(a.message_id, []).append(a)

    result: list[MessageItem] = []
    for m in messages:
        related = att_by_msg.get(m.id, [])
        result.append(
            MessageItem(
                message_id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                attachments=[
                    AttachmentBrief(
                        attachment_id=a.id,
                        file_name=a.file_name,
                        file_type=a.file_type,
                        file_size=a.file_size,
                        parse_status=a.parse_status,
                        created_at=a.created_at,
                    )
                    for a in related
                ],
            )
        )
    return result


@router.post("/ws-token", response_model=WsTokenResponse)
def create_ws_token(
    body: WsTokenRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    token, expires_in = issue_ws_token(db, user.id, body.conversation_id)
    return WsTokenResponse(websocket_token=token, expires_in=expires_in)


@router.post("/send", response_model=ChatSendResponse)
def send_message(
    body: ChatSendRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = chat_service.get_conversation_for_user(db, user.id, body.conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    if chat_service.has_running_task(db, body.conversation_id):
        raise HTTPException(status_code=409, detail="当前会话已有运行中的分析任务")
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="内容不能为空")

    msg = chat_service.add_message(db, body.conversation_id, role="user", content=body.content.strip())
    task = AnalysisTask(
        conversation_id=body.conversation_id,
        user_id=user.id,
        input_text=body.content.strip(),
        task_status="queued",
        current_step="queued",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return ChatSendResponse(task_id=task.id, message_id=msg.id, task_status=task.task_status)


@router.post("/cancel")
def cancel_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = db.get(AnalysisTask, task_id)
    if not task or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.task_status in {"success", "failed", "cancelled"}:
        return {"task_id": task.id, "task_status": task.task_status}
    task.task_status = "cancelled"
    task.current_step = "cancelled"
    task.finished_at = datetime.now(timezone.utc)
    task.error_message = "用户取消"
    db.commit()
    return {"task_id": task.id, "task_status": task.task_status}

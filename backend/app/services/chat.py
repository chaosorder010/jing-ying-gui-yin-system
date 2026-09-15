import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AnalysisResult,
    AnalysisTask,
    Attachment,
    ContextSummary,
    Conversation,
    Message,
    TaskLog,
    WebsocketToken,
)


def conversation_dirs(user_id: int, conversation_id: int) -> dict[str, Path]:
    settings = get_settings()
    return {
        "uploads": settings.upload_root / str(user_id) / str(conversation_id),
        "exports": settings.export_root / str(user_id) / str(conversation_id),
        "workspace": settings.workspace_root / str(user_id) / str(conversation_id),
    }


def ensure_conversation_dirs(user_id: int, conversation_id: int) -> dict[str, Path]:
    dirs = conversation_dirs(user_id, conversation_id)
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def delete_conversation_dirs(user_id: int, conversation_id: int) -> None:
    for path in conversation_dirs(user_id, conversation_id).values():
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def create_conversation(db: Session, user_id: int, title: str) -> Conversation:
    conv = Conversation(user_id=user_id, title=title, status="active")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    ensure_conversation_dirs(user_id, conv.id)
    return conv


def list_conversations(db: Session, user_id: int) -> list[Conversation]:
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id, Conversation.status != "deleted")
        .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.id.desc())
        .all()
    )


def get_conversation_for_user(db: Session, user_id: int, conversation_id: int) -> Conversation | None:
    return (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.status != "deleted",
        )
        .one_or_none()
    )


def update_conversation_title(db: Session, conv: Conversation, title: str) -> Conversation:
    conv.title = title
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(conv)
    return conv


def soft_delete_conversations(db: Session, user_id: int, conversation_ids: list[int]) -> int:
    count = 0
    for cid in conversation_ids:
        conv = get_conversation_for_user(db, user_id, cid)
        if not conv:
            continue
        # Cascade delete related records
        db.query(TaskLog).filter(
            TaskLog.task_id.in_(db.query(AnalysisTask.id).filter(AnalysisTask.conversation_id == cid))
        ).delete(synchronize_session=False)
        db.query(AnalysisResult).filter(AnalysisResult.conversation_id == cid).delete(synchronize_session=False)
        db.query(AnalysisTask).filter(AnalysisTask.conversation_id == cid).delete(synchronize_session=False)
        db.query(ContextSummary).filter(ContextSummary.conversation_id == cid).delete(synchronize_session=False)
        db.query(WebsocketToken).filter(WebsocketToken.conversation_id == cid).delete(synchronize_session=False)
        db.query(Attachment).filter(Attachment.conversation_id == cid).delete(synchronize_session=False)
        db.query(Message).filter(Message.conversation_id == cid).delete(synchronize_session=False)
        delete_conversation_dirs(user_id, cid)
        db.delete(conv)
        count += 1
    db.commit()
    return count


def next_seq_no(db: Session, conversation_id: int) -> int:
    current = (
        db.query(func.coalesce(func.max(Message.seq_no), 0))
        .filter(Message.conversation_id == conversation_id)
        .scalar()
    )
    return int(current) + 1


def add_message(
    db: Session,
    conversation_id: int,
    role: str,
    content: str,
    message_type: str = "text",
    tool_name: str | None = None,
    tool_status: str | None = None,
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        message_type=message_type,
        tool_name=tool_name,
        tool_status=tool_status,
        seq_no=next_seq_no(db, conversation_id),
    )
    db.add(msg)
    conv = db.get(Conversation, conversation_id)
    if conv:
        conv.last_message_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)
    return msg


def list_messages(db: Session, conversation_id: int) -> list[Message]:
    return (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.seq_no.asc(), Message.id.asc())
        .all()
    )


def has_running_task(db: Session, conversation_id: int) -> bool:
    return (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.conversation_id == conversation_id,
            AnalysisTask.task_status.in_(["queued", "running"]),
        )
        .first()
        is not None
    )

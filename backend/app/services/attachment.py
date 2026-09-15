import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.models import Attachment
from app.services.chat import ensure_conversation_dirs, get_conversation_for_user


ALLOWED_ROOT_NAMES = {"uploads", "exports", "workspace"}


def save_upload(
    db: Session, user_id: int, conversation_id: int, file: UploadFile
) -> Attachment:
    conv = get_conversation_for_user(db, user_id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    dirs = ensure_conversation_dirs(user_id, conversation_id)
    safe_name = Path(file.filename or "upload.bin").name
    unique = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    dest = dirs["uploads"] / unique

    content = file.file.read()
    dest.write_bytes(content)

    att = Attachment(
        conversation_id=conversation_id,
        file_name=safe_name,
        file_path=str(dest),
        file_type=file.content_type or "application/octet-stream",
        file_size=len(content),
        parse_status="ready",
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


def get_attachment_for_user(db: Session, user_id: int, attachment_id: int) -> Attachment:
    att = db.get(Attachment, attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="附件不存在")
    conv = get_conversation_for_user(db, user_id, att.conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="附件不存在")
    return att


def delete_attachment(db: Session, user_id: int, attachment_id: int) -> None:
    att = get_attachment_for_user(db, user_id, attachment_id)
    path = Path(att.file_path)
    if path.exists():
        path.unlink(missing_ok=True)
    db.delete(att)
    db.commit()


def list_attachments(db: Session, conversation_id: int) -> list[Attachment]:
    return (
        db.query(Attachment)
        .filter(Attachment.conversation_id == conversation_id)
        .order_by(Attachment.id.desc())
        .all()
    )

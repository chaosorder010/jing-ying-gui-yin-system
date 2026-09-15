from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import User
from app.schemas import AttachmentDeleteRequest, AttachmentUploadResponse
from app.services import attachment as attachment_service
from app.services.chat import get_conversation_for_user

router = APIRouter(prefix="/api/attachment", tags=["attachment"])


@router.post("/upload", response_model=AttachmentUploadResponse)
async def upload_attachment(
    conversation_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    att = attachment_service.save_upload(db, user.id, conversation_id, file)
    return AttachmentUploadResponse(
        attachment_id=att.id, file_name=att.file_name, file_path=att.file_path
    )


@router.post("/delete")
def delete_attachment(
    body: AttachmentDeleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    attachment_service.delete_attachment(db, user.id, body.attachment_id)
    return {"status": "ok"}


@router.get("/get")
def get_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    att = attachment_service.get_attachment_for_user(db, user.id, attachment_id)
    path = Path(att.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=att.file_name, media_type=att.file_type)


@router.get("/ls/{conversation_id}")
def list_conversation_attachments(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = get_conversation_for_user(db, user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    items = attachment_service.list_attachments(db, conversation_id)
    return [
        {
            "attachment_id": a.id,
            "file_name": a.file_name,
            "file_type": a.file_type,
            "file_size": a.file_size,
            "parse_status": a.parse_status,
            "created_at": a.created_at,
        }
        for a in items
    ]

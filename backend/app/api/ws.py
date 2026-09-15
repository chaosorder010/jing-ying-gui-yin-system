import asyncio
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.analysis.engine import run_analysis_task
from app.database import SessionLocal
from app.models import AnalysisTask, WebsocketToken
from app.websocket.manager import manager
from datetime import datetime, timezone

router = APIRouter(tags=["websocket"])


def _validate_ws_token(db: Session, token: str, conversation_id: int) -> WebsocketToken:
    row = db.query(WebsocketToken).filter(WebsocketToken.token == token).one_or_none()
    if not row:
        raise ValueError("websocket token 无效")
    now = datetime.now(timezone.utc)
    exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if exp < now:
        raise ValueError("websocket token 已过期")
    if row.consumed_at is not None:
        raise ValueError("websocket token 已使用")
    if row.conversation_id != conversation_id:
        raise ValueError("conversation 不匹配")
    row.consumed_at = now
    db.commit()
    db.refresh(row)
    return row


@router.websocket("/api/chat/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    websocket_token: str = Query(...),
    conversation_id: int = Query(...),
):
    db: Session = SessionLocal()
    try:
        token_row = _validate_ws_token(db, websocket_token, conversation_id)
        user_id = token_row.user_id
    except Exception as exc:
        # Must accept before close, otherwise clients see HTTP 403
        await websocket.accept()
        await websocket.send_json({"type": "error", "error_message": str(exc)})
        await websocket.close(code=1008)
        db.close()
        return

    await manager.connect(conversation_id, websocket)
    active_task: asyncio.Task | None = None

    async def emit(message: dict) -> None:
        await manager.broadcast(conversation_id, message)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "error_message": "无效 JSON"})
                continue

            action = data.get("action")
            if action == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if action == "start_task":
                task_id = int(data.get("task_id", 0))
                task = db.get(AnalysisTask, task_id)
                if not task or task.conversation_id != conversation_id or task.user_id != user_id:
                    await websocket.send_json({"type": "error", "error_message": "任务不存在"})
                    continue
                if task.task_status not in {"queued", "running"}:
                    await websocket.send_json({"type": "error", "error_message": "任务状态不可启动"})
                    continue
                if active_task and not active_task.done():
                    await websocket.send_json({"type": "error", "error_message": "已有任务在运行"})
                    continue
                active_task = asyncio.create_task(run_analysis_task(task_id, emit))
                continue

            if action == "cancel_task":
                task_id = int(data.get("task_id", 0))
                task = db.get(AnalysisTask, task_id)
                if task and task.user_id == user_id and task.task_status in {"queued", "running"}:
                    task.task_status = "cancelled"
                    task.current_step = "cancelled"
                    db.commit()
                    await emit({"type": "error", "task_id": task_id, "error_message": "任务已取消"})
                continue

            await websocket.send_json({"type": "error", "error_message": f"未知 action: {action}"})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(conversation_id, websocket)
        db.close()

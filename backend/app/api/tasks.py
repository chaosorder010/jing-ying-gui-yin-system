from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_admin
from app.database import get_db
from app.models import AnalysisResult, AnalysisTask, SystemConfig, TaskLog, User
from app.schemas import ReloadResponse, ResultResponse, TaskStatusResponse
from app.services.config_service import reload_configs
from app.services.chat import get_conversation_for_user

router = APIRouter(prefix="/api", tags=["tasks"])


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = db.get(AnalysisTask, task_id)
    if not task or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskStatusResponse(
        task_status=task.task_status,
        current_step=task.current_step,
        started_at=task.started_at,
        finished_at=task.finished_at,
        error_message=task.error_message,
    )


@router.get("/results/{task_id}", response_model=ResultResponse)
def get_result(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = db.get(AnalysisTask, task_id)
    if not task or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    result = db.query(AnalysisResult).filter(AnalysisResult.task_id == task_id).one_or_none()
    if not result:
        raise HTTPException(status_code=404, detail="结果不存在")
    return ResultResponse(
        problem_definition=result.problem_definition,
        key_metrics=result.key_metrics_json or [],
        evidence_list=result.evidence_list_json or [],
        conclusion_text=result.conclusion_text,
        missing_data_text=result.missing_data_text,
        next_action_text=result.next_action_text,
        result_markdown=result.result_markdown,
        result_file_path=result.result_file_path,
        result_id=result.id,
    )


@router.get("/results/{task_id}/download")
def download_result(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = db.get(AnalysisTask, task_id)
    if not task or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    result = db.query(AnalysisResult).filter(AnalysisResult.task_id == task_id).one_or_none()
    if not result or not result.result_file_path:
        raise HTTPException(status_code=404, detail="结果文件不存在")
    path = Path(result.result_file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="结果文件不存在")
    return FileResponse(path, filename=path.name, media_type="text/markdown")


@router.get("/tasks/{task_id}/logs")
def get_task_logs(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = db.get(AnalysisTask, task_id)
    if not task or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    logs = (
        db.query(TaskLog)
        .filter(TaskLog.task_id == task_id)
        .order_by(TaskLog.id.asc())
        .all()
    )
    return [
        {
            "id": log.id,
            "log_level": log.log_level,
            "log_type": log.log_type,
            "log_content": log.log_content,
            "created_at": log.created_at,
        }
        for log in logs
    ]


@router.post("/admin/reload", response_model=ReloadResponse)
def admin_reload(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    configs = reload_configs(db)
    return ReloadResponse(status="ok", message=f"已重载 {len(configs)} 项配置")


@router.get("/admin/configs")
def list_configs(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    rows = db.query(SystemConfig).order_by(SystemConfig.config_group, SystemConfig.config_key).all()
    return [
        {
            "config_key": r.config_key,
            "config_value": r.config_value,
            "config_group": r.config_group,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


@router.get("/conversations/{conversation_id}/latest-result", response_model=ResultResponse | None)
def latest_result(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = get_conversation_for_user(db, user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    result = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.conversation_id == conversation_id)
        .order_by(AnalysisResult.id.desc())
        .first()
    )
    if not result:
        return None
    return ResultResponse(
        problem_definition=result.problem_definition,
        key_metrics=result.key_metrics_json or [],
        evidence_list=result.evidence_list_json or [],
        conclusion_text=result.conclusion_text,
        missing_data_text=result.missing_data_text,
        next_action_text=result.next_action_text,
        result_markdown=result.result_markdown,
        result_file_path=result.result_file_path,
        result_id=result.id,
    )

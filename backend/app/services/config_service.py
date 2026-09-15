from datetime import datetime, timedelta, timezone
import secrets

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import SystemConfig, WebsocketToken
from app.services.chat import get_conversation_for_user
from fastapi import HTTPException


def issue_ws_token(db: Session, user_id: int, conversation_id: int) -> tuple[str, int]:
    conv = get_conversation_for_user(db, user_id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(seconds=settings.ws_token_ttl_seconds)
    row = WebsocketToken(
        user_id=user_id,
        conversation_id=conversation_id,
        token=token,
        expires_at=expires,
    )
    db.add(row)
    db.commit()
    return token, settings.ws_token_ttl_seconds


def consume_ws_token(db: Session, token: str, conversation_id: int) -> WebsocketToken:
    row = db.query(WebsocketToken).filter(WebsocketToken.token == token).one_or_none()
    if not row:
        raise HTTPException(status_code=401, detail="websocket token 无效")
    now = datetime.now(timezone.utc)
    exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if exp < now:
        raise HTTPException(status_code=401, detail="websocket token 已过期")
    if row.consumed_at is not None:
        raise HTTPException(status_code=401, detail="websocket token 已使用")
    if row.conversation_id != conversation_id:
        raise HTTPException(status_code=401, detail="conversation 不匹配")
    row.consumed_at = now
    db.commit()
    db.refresh(row)
    return row


_runtime_config: dict[str, str] = {}


def load_configs(db: Session) -> dict[str, str]:
    global _runtime_config
    rows = db.query(SystemConfig).all()
    _runtime_config = {r.config_key: r.config_value for r in rows}
    return dict(_runtime_config)


def get_config(key: str, default: str = "") -> str:
    return _runtime_config.get(key, default)


def reload_configs(db: Session) -> dict[str, str]:
    from app.config import reload_settings

    reload_settings()
    return load_configs(db)


def ensure_default_configs(db: Session) -> None:
    defaults = [
        ("analysis.engine", "auto", "analysis"),
        ("analysis.max_tools", "8", "analysis"),
        ("feature.export_enabled", "true", "feature"),
        ("feature.command_tool", "false", "feature"),
    ]
    for key, value, group in defaults:
        exists = db.query(SystemConfig).filter(SystemConfig.config_key == key).one_or_none()
        if not exists:
            db.add(SystemConfig(config_key=key, config_value=value, config_group=group))
    db.commit()
    load_configs(db)

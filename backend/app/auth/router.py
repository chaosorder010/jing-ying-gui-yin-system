from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import COOKIE_NAME, create_access_token, get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import User
from urllib.parse import urlencode
from fastapi import HTTPException, Query
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def auth_login(role: str = Query(default="analyst")):
    """Mock OAuth: redirect to frontend callback with a fake authorization code."""
    settings = get_settings()
    if settings.auth_mode != "mock":
        raise HTTPException(status_code=501, detail="仅支持 mock 认证模式")
    code = "mock_admin" if role == "admin" else "mock_analyst"
    params = urlencode({"code": code})
    return RedirectResponse(
        url=f"{settings.frontend_url}/login/callback?{params}",
        status_code=302,
    )


@router.get("/callback")
def auth_callback(code: str = Query(...), db: Session = Depends(get_db)):
    if code == "mock_admin":
        external_id, username, display_name, role = "mock-admin-1", "admin", "系统管理员", "admin"
    else:
        external_id, username, display_name, role = "mock-user-1", "analyst", "分析用户", "analyst"

    user = db.query(User).filter(User.external_user_id == external_id).one_or_none()
    if not user:
        user = User(
            external_user_id=external_id,
            username=username,
            display_name=display_name,
            role=role,
            status="active",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
        },
    }


@router.get("/me")
def auth_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
    }

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, tasks, ws
from app.api import attachment as attachment_api
from app.auth.router import router as auth_router
from app.config import get_settings
from app.database import SessionLocal
from app.services.config_service import ensure_default_configs


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    for root in (settings.upload_root, settings.export_root, settings.workspace_root, settings.data_root):
        Path(root).mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        ensure_default_configs(db)
    finally:
        db.close()
    yield


app = FastAPI(title="经营归因分析系统", version="1.0.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat.router)
app.include_router(attachment_api.router)
app.include_router(tasks.router)
app.include_router(ws.router)


@app.get("/health")
def health():
    return {"status": "ok"}

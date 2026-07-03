"""VoiceStruct Core MVP — FastAPI 진입점 (ARCHITECTURE §7)."""

from fastapi import FastAPI

from app.api import audio_routes, stt_routes, structure_routes
from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import register_exception_handlers

app = FastAPI(title=settings.app_name, version=settings.version)

register_exception_handlers(app)
app.include_router(audio_routes.router)
app.include_router(stt_routes.router)
app.include_router(structure_routes.router)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/")
def health():
    return {"ok": True, "service": settings.app_name, "version": settings.version}

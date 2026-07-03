"""음성 업로드 API (DB명세 6.2)."""

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import audio_service

router = APIRouter(prefix="/api/audio", tags=["audio"])


@router.post("/upload", status_code=201)
def upload_audio(
    user_id: str = Form(...),
    domain: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    result = audio_service.upload(db, user_id, domain, file)
    return JSONResponse(status_code=201, content=result)

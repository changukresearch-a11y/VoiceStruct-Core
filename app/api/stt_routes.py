"""Mock STT 실행 API (DB명세 6.3)."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.transcript_schema import SttTranscribeRequest
from app.services import stt_service

router = APIRouter(prefix="/api/stt", tags=["stt"])


@router.post("/transcribe", status_code=201)
def transcribe(req: SttTranscribeRequest, db: Session = Depends(get_db)):
    result = stt_service.transcribe(db, req.audio_id)
    return JSONResponse(status_code=201, content=result)

"""STT API 스키마 (DB명세 7.3)."""

from pydantic import BaseModel


class SttTranscribeRequest(BaseModel):
    audio_id: str


class SttTranscribeResponse(BaseModel):
    ok: bool
    audio_id: str
    transcript_id: str
    stt_provider: str
    stt_status: str

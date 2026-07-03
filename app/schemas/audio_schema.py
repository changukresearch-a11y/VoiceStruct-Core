"""Audio API 스키마 (DB명세 7.2)."""

from pydantic import BaseModel


class AudioUploadResponse(BaseModel):
    ok: bool
    audio_id: str
    status: str
    file_path: str

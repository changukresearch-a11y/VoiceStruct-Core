"""AudioRecord DB 접근 (찾으면 객체 / 없으면 None; 404 판단은 서비스)."""

from sqlalchemy.orm import Session

from app.core.time_utils import now
from app.models.audio_record import AudioRecord


class AudioRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **fields) -> AudioRecord:
        rec = AudioRecord(**fields)
        self.db.add(rec)
        self.db.flush()
        return rec

    def get_by_audio_id(self, audio_id: str) -> AudioRecord | None:
        return (
            self.db.query(AudioRecord)
            .filter(AudioRecord.audio_id == audio_id)
            .first()
        )

    def update_status(self, rec: AudioRecord, status: str) -> None:
        rec.status = status
        rec.updated_at = now()  # D-01
        self.db.flush()

"""TranscriptRecord DB 접근."""

from sqlalchemy.orm import Session

from app.models.transcript_record import TranscriptRecord


class TranscriptRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **fields) -> TranscriptRecord:
        rec = TranscriptRecord(**fields)
        self.db.add(rec)
        self.db.flush()
        return rec

    def get_by_transcript_id(self, transcript_id: str) -> TranscriptRecord | None:
        return (
            self.db.query(TranscriptRecord)
            .filter(TranscriptRecord.transcript_id == transcript_id)
            .first()
        )

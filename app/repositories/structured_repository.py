"""StructuredRecord DB 접근."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.structured_record import StructuredRecord


class StructuredRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **fields) -> StructuredRecord:
        rec = StructuredRecord(**fields)
        self.db.add(rec)
        self.db.flush()
        return rec

    def get_by_structured_id(self, structured_id: str) -> StructuredRecord | None:
        return (
            self.db.query(StructuredRecord)
            .filter(StructuredRecord.structured_id == structured_id)
            .first()
        )

    def save_user_json(
        self,
        rec: StructuredRecord,
        user_confirmed_json: str,
        status: str,
        updated_at: datetime,
    ) -> None:
        rec.user_confirmed_json = user_confirmed_json
        rec.status = status
        rec.updated_at = updated_at
        self.db.flush()

    def flush(self, rec: StructuredRecord) -> None:
        self.db.flush()

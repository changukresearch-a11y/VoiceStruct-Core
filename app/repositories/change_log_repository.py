"""ChangeLog DB 접근."""

from sqlalchemy.orm import Session

from app.models.change_log import ChangeLog


class ChangeLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **fields) -> ChangeLog:
        rec = ChangeLog(**fields)
        self.db.add(rec)
        self.db.flush()
        return rec

    def list_by_structured_id(self, structured_id: str) -> list[ChangeLog]:
        return (
            self.db.query(ChangeLog)
            .filter(ChangeLog.structured_id == structured_id)
            .order_by(ChangeLog.id)
            .all()
        )

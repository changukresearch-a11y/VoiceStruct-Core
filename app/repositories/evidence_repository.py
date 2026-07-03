"""EvidenceRecord DB 접근."""

from sqlalchemy.orm import Session

from app.models.evidence_record import EvidenceRecord


class EvidenceRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **fields) -> EvidenceRecord:
        rec = EvidenceRecord(**fields)
        self.db.add(rec)
        self.db.flush()
        return rec

    def list_by_structured_id(self, structured_id: str) -> list[EvidenceRecord]:
        return (
            self.db.query(EvidenceRecord)
            .filter(EvidenceRecord.structured_id == structured_id)
            .order_by(EvidenceRecord.id)
            .all()
        )

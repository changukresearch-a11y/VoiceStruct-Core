"""evidence_records 테이블 (DB명세 3.4)."""

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from app.core.database import Base


class EvidenceRecord(Base):
    __tablename__ = "evidence_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    evidence_id = Column(String, unique=True, index=True, nullable=False)
    structured_id = Column(String, index=True, nullable=False)
    field_name = Column(String, index=True, nullable=False)
    field_value = Column(String, nullable=False)
    evidence_text = Column(Text, nullable=False)
    start_time = Column(Float, nullable=True)
    end_time = Column(Float, nullable=True)
    speaker = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False)

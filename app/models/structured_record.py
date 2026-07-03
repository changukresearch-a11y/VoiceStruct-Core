"""structured_records 테이블 (DB명세 3.3)."""

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.core.database import Base


class StructuredRecord(Base):
    __tablename__ = "structured_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    structured_id = Column(String, unique=True, index=True, nullable=False)
    audio_id = Column(String, index=True, nullable=False)
    transcript_id = Column(String, index=True, nullable=False)
    domain = Column(String, index=True, nullable=False)
    schema_version = Column(String, index=True, nullable=False)
    ai_structured_json = Column(Text, nullable=False)
    user_confirmed_json = Column(Text, nullable=True)
    status = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)

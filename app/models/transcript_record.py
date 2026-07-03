"""transcript_records 테이블 (DB명세 3.2)."""

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from app.core.database import Base


class TranscriptRecord(Base):
    __tablename__ = "transcript_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transcript_id = Column(String, unique=True, index=True, nullable=False)
    audio_id = Column(String, index=True, nullable=False)
    stt_provider = Column(String, index=True, nullable=False)
    language = Column(String, nullable=False)
    raw_transcript = Column(Text, nullable=False)
    cleaned_transcript = Column(Text, nullable=False)
    segments_json = Column(Text, nullable=False)
    confidence_avg = Column(Float, nullable=True)
    stt_status = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, nullable=False)

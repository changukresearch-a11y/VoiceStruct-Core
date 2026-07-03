"""audio_records 테이블 (DB명세 3.1, D-01: updated_at 포함)."""

from sqlalchemy import Column, DateTime, Float, Integer, String

from app.core.database import Base


class AudioRecord(Base):
    __tablename__ = "audio_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_id = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    domain = Column(String, index=True, nullable=False)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    duration_sec = Column(Float, nullable=True)
    status = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=True)  # D-01

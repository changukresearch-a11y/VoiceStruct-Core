"""change_logs 테이블 (DB명세 3.5)."""

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.core.database import Base


class ChangeLog(Base):
    __tablename__ = "change_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    change_id = Column(String, unique=True, index=True, nullable=False)
    structured_id = Column(String, index=True, nullable=False)
    changed_fields_json = Column(Text, nullable=False)
    previous_value_json = Column(Text, nullable=False)
    new_value_json = Column(Text, nullable=False)
    changed_by = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, nullable=False)

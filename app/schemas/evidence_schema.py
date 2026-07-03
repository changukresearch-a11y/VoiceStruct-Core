"""Evidence API 스키마 (DB명세 7.7)."""

from pydantic import BaseModel


class EvidenceItem(BaseModel):
    evidence_id: str
    field_name: str
    field_value: str
    evidence_text: str
    start_time: float | None = None
    end_time: float | None = None
    speaker: str | None = None
    confidence: float | None = None


class EvidenceListResponse(BaseModel):
    ok: bool
    structured_id: str
    evidence: list[EvidenceItem]

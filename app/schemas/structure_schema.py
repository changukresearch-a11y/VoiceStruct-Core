"""Structure API 스키마 (DB명세 7.4~7.6).

CareBaseStructuredJson은 구조화 결과의 계약(contract)이자
Phase2에서 Claude API의 output_format으로도 재사용된다.
"""

from typing import Any

from pydantic import BaseModel


class RiskSignalCandidate(BaseModel):
    category: str
    evidence_text: str
    strength: int
    notice: str


class CareBaseStructuredJson(BaseModel):
    domain: str
    schema_version: str
    memory_summary: str
    people: list[str]
    places: list[str]
    time_reference: str | None = None
    emotion: list[str]
    topic: str | None = None
    memory_type: str
    risk_signal_candidates: list[RiskSignalCandidate]
    missing_fields: list[str]
    requires_user_confirmation: bool
    safety_notice: str


class StructureRunRequest(BaseModel):
    transcript_id: str
    domain: str


class StructureRunResponse(BaseModel):
    ok: bool
    structured_id: str
    status: str
    structured_json: CareBaseStructuredJson
    evidence_count: int


class StructureUpdateRequest(BaseModel):
    changed_by: str
    edited_fields: dict[str, Any]


class StructureUpdateResponse(BaseModel):
    ok: bool
    structured_id: str
    status: str
    changed_fields: list[str]


class StructureConfirmRequest(BaseModel):
    confirmed_by: str


class StructureConfirmResponse(BaseModel):
    ok: bool
    structured_id: str
    status: str
    confirmed_at: str | None = None
    message: str | None = None

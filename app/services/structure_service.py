"""CareBase 구조화/조회/수정 서비스 (DB명세 6.4~6.6, 6.8~6.9, ARCHITECTURE §5.2~5.3)."""

from sqlalchemy.orm import Session

from app.core import constants as C
from app.core import json_utils
from app.core.exceptions import (
    AlreadyConfirmedError,
    InvalidDomainError,
    StructuredRecordNotFoundError,
    StructureError,
    TranscriptNotFoundError,
)
from app.core.id_utils import new_change_id, new_evidence_id, new_structured_id
from app.core.time_utils import iso, now
from app.domains.carebase import evidence_mapper, extractor, safety_rules
from app.repositories.audio_repository import AudioRepository
from app.repositories.change_log_repository import ChangeLogRepository
from app.repositories.evidence_repository import EvidenceRepository
from app.repositories.structured_repository import StructuredRepository
from app.repositories.transcript_repository import TranscriptRepository


def run(db: Session, transcript_id: str, domain: str) -> dict:
    if domain not in C.ALLOWED_DOMAINS:
        raise InvalidDomainError()

    tr = TranscriptRepository(db).get_by_transcript_id(transcript_id)
    if not tr:
        raise TranscriptNotFoundError()

    segments = json_utils.loads(tr.segments_json) or []
    try:
        draft = extractor.extract(tr.cleaned_transcript, segments)
        draft = safety_rules.apply(draft)
        evidences = evidence_mapper.map(draft, segments)
    except Exception as e:  # noqa: BLE001
        raise StructureError() from e

    structured_id = new_structured_id()
    StructuredRepository(db).create(
        structured_id=structured_id,
        audio_id=tr.audio_id,
        transcript_id=transcript_id,
        domain=domain,
        schema_version=draft["schema_version"],
        ai_structured_json=json_utils.dumps(draft),
        user_confirmed_json=None,
        status=C.AI_TEMP,
        created_at=now(),
        updated_at=None,
        confirmed_at=None,
    )

    evidence_repo = EvidenceRepository(db)
    for ev in evidences:
        evidence_repo.create(
            evidence_id=new_evidence_id(),
            structured_id=structured_id,
            created_at=now(),
            **ev,
        )

    audio_repo = AudioRepository(db)
    audio = audio_repo.get_by_audio_id(tr.audio_id)
    if audio:
        audio_repo.update_status(audio, C.STRUCTURED)

    return {
        "ok": True,
        "structured_id": structured_id,
        "status": C.AI_TEMP,
        "structured_json": draft,  # D-02: run 응답 키는 structured_json
        "evidence_count": len(evidences),
    }


def get_detail(db: Session, structured_id: str) -> dict:
    rec = StructuredRepository(db).get_by_structured_id(structured_id)
    if not rec:
        raise StructuredRecordNotFoundError()

    evidences = EvidenceRepository(db).list_by_structured_id(structured_id)
    return {
        "ok": True,
        "structured_id": rec.structured_id,
        "audio_id": rec.audio_id,
        "transcript_id": rec.transcript_id,
        "domain": rec.domain,
        "schema_version": rec.schema_version,
        "status": rec.status,
        # D-02: get 응답 키는 ai_structured_json / user_confirmed_json
        "ai_structured_json": json_utils.loads(rec.ai_structured_json),
        "user_confirmed_json": json_utils.loads(rec.user_confirmed_json),
        "evidence": [
            {
                "evidence_id": e.evidence_id,
                "field_name": e.field_name,
                "field_value": e.field_value,
                "evidence_text": e.evidence_text,
                "start_time": e.start_time,
                "end_time": e.end_time,
                "speaker": e.speaker,
                "confidence": e.confidence,
            }
            for e in evidences
        ],
        "created_at": iso(rec.created_at),
        "updated_at": iso(rec.updated_at),
        "confirmed_at": iso(rec.confirmed_at),
    }


def update(db: Session, structured_id: str, changed_by: str, edited_fields: dict) -> dict:
    repo = StructuredRepository(db)
    rec = repo.get_by_structured_id(structured_id)
    if not rec:
        raise StructuredRecordNotFoundError()
    if rec.status == C.USER_CONFIRMED:
        raise AlreadyConfirmedError()  # 409

    # 기준 JSON 결정 (DB명세 6.6 처리순서 4)
    base = json_utils.loads(rec.user_confirmed_json) or json_utils.loads(
        rec.ai_structured_json
    )
    previous = {k: base.get(k) for k in edited_fields}
    merged = {**base, **edited_fields}
    merged = safety_rules.apply(merged)  # 수정에도 안전규칙 (DB명세 13.5)

    repo.save_user_json(
        rec,
        json_utils.dumps(merged),
        status=C.USER_EDITED,
        updated_at=now(),
    )

    ChangeLogRepository(db).create(
        change_id=new_change_id(),
        structured_id=structured_id,
        changed_fields_json=json_utils.dumps(list(edited_fields.keys())),
        previous_value_json=json_utils.dumps(previous),
        new_value_json=json_utils.dumps({k: merged.get(k) for k in edited_fields}),
        changed_by=changed_by,
        created_at=now(),
    )

    return {
        "ok": True,
        "structured_id": structured_id,
        "status": C.USER_EDITED,
        "changed_fields": list(edited_fields.keys()),
    }


def list_evidence(db: Session, structured_id: str) -> dict:
    rec = StructuredRepository(db).get_by_structured_id(structured_id)
    if not rec:
        raise StructuredRecordNotFoundError()
    evidences = EvidenceRepository(db).list_by_structured_id(structured_id)
    return {
        "ok": True,
        "structured_id": structured_id,
        "evidence": [
            {
                "evidence_id": e.evidence_id,
                "field_name": e.field_name,
                "field_value": e.field_value,
                "evidence_text": e.evidence_text,
                "start_time": e.start_time,
                "end_time": e.end_time,
                "speaker": e.speaker,
                "confidence": e.confidence,
            }
            for e in evidences
        ],
    }


def list_changes(db: Session, structured_id: str) -> dict:
    rec = StructuredRepository(db).get_by_structured_id(structured_id)
    if not rec:
        raise StructuredRecordNotFoundError()
    changes = ChangeLogRepository(db).list_by_structured_id(structured_id)
    return {
        "ok": True,
        "structured_id": structured_id,
        "changes": [
            {
                "change_id": c.change_id,
                "changed_fields": json_utils.loads(c.changed_fields_json),
                "previous_value": json_utils.loads(c.previous_value_json),
                "new_value": json_utils.loads(c.new_value_json),
                "changed_by": c.changed_by,
                "created_at": iso(c.created_at),
            }
            for c in changes
        ],
    }

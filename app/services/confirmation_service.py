"""사용자 확정 서비스 (DB명세 6.7, ARCHITECTURE §5.4).

멱등 처리: 이미 확정된 기록에 재요청 시 200 반환.
"""

from sqlalchemy.orm import Session

from app.core import constants as C
from app.core.exceptions import StructuredRecordNotFoundError
from app.core.time_utils import iso, now
from app.repositories.audio_repository import AudioRepository
from app.repositories.structured_repository import StructuredRepository


def confirm(db: Session, structured_id: str, confirmed_by: str) -> dict:
    repo = StructuredRepository(db)
    rec = repo.get_by_structured_id(structured_id)
    if not rec:
        raise StructuredRecordNotFoundError()

    # 멱등 처리 (DB명세 6.7)
    if rec.status == C.USER_CONFIRMED:
        return {
            "ok": True,
            "structured_id": structured_id,
            "status": C.USER_CONFIRMED,
            "message": "이미 확정된 기록입니다.",
        }

    # 수정 없이 확정 → AI 초안을 user_confirmed_json에 복사
    if not rec.user_confirmed_json:
        rec.user_confirmed_json = rec.ai_structured_json
    rec.status = C.USER_CONFIRMED
    rec.confirmed_at = now()
    repo.flush(rec)

    audio_repo = AudioRepository(db)
    audio = audio_repo.get_by_audio_id(rec.audio_id)
    if audio:
        audio_repo.update_status(audio, C.CONFIRMED)

    # TODO(Phase2): UserConfirmationLog에 confirmed_by 기록 (D-06)
    return {
        "ok": True,
        "structured_id": structured_id,
        "status": C.USER_CONFIRMED,
        "confirmed_at": iso(rec.confirmed_at),
    }

"""Mock STT 실행 서비스 (DB명세 6.3, ARCHITECTURE §5.1)."""

from sqlalchemy.orm import Session

from app.core import constants as C
from app.core import json_utils
from app.core.exceptions import (
    AudioNotFoundError,
    InvalidStatusTransitionError,
    SttError,
)
from app.core.id_utils import new_transcript_id
from app.core.time_utils import now
from app.providers.registry import get_stt_provider
from app.repositories.audio_repository import AudioRepository
from app.repositories.transcript_repository import TranscriptRepository


def transcribe(db: Session, audio_id: str) -> dict:
    audio_repo = AudioRepository(db)
    audio = audio_repo.get_by_audio_id(audio_id)
    if not audio:
        raise AudioNotFoundError()

    # 상태 검증 (DB명세 6.3 처리순서 2)
    if audio.status not in (C.AUDIO_RECEIVED, C.AUDIO_FAILED):
        raise InvalidStatusTransitionError(
            f"현재 상태 {audio.status}에서는 STT를 실행할 수 없습니다."
        )

    provider = get_stt_provider()
    try:
        result = provider.transcribe(audio.file_path, language="ko-KR")
    except Exception as e:  # noqa: BLE001
        audio_repo.update_status(audio, C.AUDIO_FAILED)
        raise SttError() from e

    transcript_id = new_transcript_id()
    TranscriptRepository(db).create(
        transcript_id=transcript_id,
        audio_id=audio_id,
        stt_provider=result.stt_provider,
        language=result.language,
        raw_transcript=result.raw_transcript,
        cleaned_transcript=result.cleaned_transcript,
        segments_json=json_utils.dumps(result.segments),
        confidence_avg=result.confidence_avg,
        stt_status=result.stt_status,
        created_at=now(),
    )

    # 실제 Provider가 길이를 반환하면 AudioRecord에 반영 (Mock도 13.0 반환)
    if result.duration_sec is not None:
        audio.duration_sec = result.duration_sec
    audio_repo.update_status(audio, C.STT_COMPLETED)

    return {
        "ok": True,
        "audio_id": audio_id,
        "transcript_id": transcript_id,
        "stt_provider": result.stt_provider,
        "stt_status": result.stt_status,
    }

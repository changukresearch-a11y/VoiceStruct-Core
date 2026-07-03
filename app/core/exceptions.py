"""도메인 예외 + 공통 에러 핸들러 (ARCHITECTURE §1).

서비스는 도메인 예외만 던지고, 핸들러 1곳이 공통 포맷으로 변환한다.
응답 포맷: {"ok": false, "error": {"code": ..., "message": ...}}
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core import constants as C


class VoiceStructError(Exception):
    code: str = C.INTERNAL_SERVER_ERROR
    http_status: int = 500
    default_message: str = "서버 내부 오류가 발생했습니다."

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)


class InvalidDomainError(VoiceStructError):
    code = C.INVALID_DOMAIN
    http_status = 400
    default_message = "MVP에서는 carebase_memory 도메인만 지원합니다."


class AudioNotFoundError(VoiceStructError):
    code = C.AUDIO_NOT_FOUND
    http_status = 404
    default_message = "해당 audio_id를 찾을 수 없습니다."


class TranscriptNotFoundError(VoiceStructError):
    code = C.TRANSCRIPT_NOT_FOUND
    http_status = 404
    default_message = "해당 transcript_id를 찾을 수 없습니다."


class StructuredRecordNotFoundError(VoiceStructError):
    code = C.STRUCTURED_RECORD_NOT_FOUND
    http_status = 404
    default_message = "해당 structured_id를 찾을 수 없습니다."


class AlreadyConfirmedError(VoiceStructError):
    code = C.ALREADY_CONFIRMED
    http_status = 409
    default_message = "이미 확정된 구조화 기록은 수정할 수 없습니다."


class FileUploadError(VoiceStructError):
    code = C.FILE_UPLOAD_FAILED
    http_status = 500
    default_message = "파일 업로드 중 오류가 발생했습니다."


class SttError(VoiceStructError):
    code = C.STT_FAILED
    http_status = 500
    default_message = "Mock STT 처리 중 오류가 발생했습니다."


class StructureError(VoiceStructError):
    code = C.STRUCTURE_FAILED
    http_status = 500
    default_message = "CareBase 구조화 처리 중 오류가 발생했습니다."


class InvalidStatusTransitionError(VoiceStructError):
    code = C.INVALID_STATUS_TRANSITION
    http_status = 409
    default_message = "허용되지 않은 상태 전이입니다."


async def _voicestruct_handler(request: Request, exc: VoiceStructError):
    return JSONResponse(
        status_code=exc.http_status,
        content={"ok": False, "error": {"code": exc.code, "message": exc.message}},
    )


async def _unhandled_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "error": {
                "code": C.INTERNAL_SERVER_ERROR,
                "message": "서버 내부 오류가 발생했습니다.",
            },
        },
    )


def register_exception_handlers(app) -> None:
    app.add_exception_handler(VoiceStructError, _voicestruct_handler)
    app.add_exception_handler(Exception, _unhandled_handler)

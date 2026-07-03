"""음성 업로드 서비스 (DB명세 6.2)."""

import os
import shutil

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core import constants as C
from app.core.config import settings
from app.core.exceptions import FileUploadError, InvalidDomainError
from app.core.id_utils import new_audio_id
from app.core.time_utils import now
from app.repositories.audio_repository import AudioRepository


def _ext(filename: str) -> str:
    _, ext = os.path.splitext(filename or "")
    return ext.lstrip(".").lower() or "wav"


def upload(db: Session, user_id: str, domain: str, file: UploadFile) -> dict:
    if domain not in C.ALLOWED_DOMAINS:
        raise InvalidDomainError()

    audio_id = new_audio_id()
    file_type = _ext(file.filename)
    os.makedirs(settings.audio_storage_dir, exist_ok=True)
    file_path = f"{settings.audio_storage_dir}/{audio_id}.{file_type}"

    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:  # noqa: BLE001
        raise FileUploadError() from e

    repo = AudioRepository(db)
    repo.create(
        audio_id=audio_id,
        user_id=user_id,
        domain=domain,
        file_name=file.filename or f"{audio_id}.{file_type}",
        file_path=file_path,
        file_type=file_type,
        duration_sec=None,
        status=C.AUDIO_RECEIVED,
        created_at=now(),
        updated_at=None,
    )

    return {
        "ok": True,
        "audio_id": audio_id,
        "status": C.AUDIO_RECEIVED,
        "file_path": file_path,
    }

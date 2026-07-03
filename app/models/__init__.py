"""모든 모델을 여기서 import 하여 Base.metadata에 등록한다."""

from app.models.audio_record import AudioRecord
from app.models.change_log import ChangeLog
from app.models.evidence_record import EvidenceRecord
from app.models.structured_record import StructuredRecord
from app.models.transcript_record import TranscriptRecord

__all__ = [
    "AudioRecord",
    "TranscriptRecord",
    "StructuredRecord",
    "EvidenceRecord",
    "ChangeLog",
]

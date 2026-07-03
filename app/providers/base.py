"""STT Provider 인터페이스 (PHASE2_ENGINE §1.1).

교체 가능한 두 축 중 'STT Provider 축'의 계약(contract).
Mock ↔ CLOVA ↔ RTZR ↔ Google 어떤 구현이 와도 이 Protocol만 만족하면
파이프라인(stt_service)은 불변이다.

segments는 파이프라인 전체에서 list[dict] 형태로 흐른다
(segments_json → json_utils.loads → extractor/evidence_mapper). 일관성 유지를 위해
TranscriptResult.segments도 list[dict]로 둔다.
각 segment dict 키: start_time, end_time, speaker, text, confidence
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class TranscriptResult:
    stt_provider: str
    language: str
    raw_transcript: str
    cleaned_transcript: str
    segments: list[dict] = field(default_factory=list)
    confidence_avg: float | None = None
    stt_status: str = "SUCCESS"
    duration_sec: float | None = None


@runtime_checkable
class SttProvider(Protocol):
    name: str

    def transcribe(self, audio_path: str, language: str = "ko-KR") -> TranscriptResult:
        ...

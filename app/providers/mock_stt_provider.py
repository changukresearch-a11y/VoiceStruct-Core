"""Mock STT Provider (지시서 9, DB명세 6.3).

실제 음성을 분석하지 않고 고정된 테스트용 STT 결과를 반환한다.
providers/base.py의 SttProvider Protocol을 만족하므로 실제 Provider와 교체 가능.
NOTE(Phase2): clova/rtzr/google Provider도 같은 Protocol로 구현하면 registry에서만 교체.
"""

from app.core import constants as C
from app.providers.base import TranscriptResult

# 고정 테스트 데이터 (기존 값 유지 — 테스트 기대값과 연동)
_RAW = (
    "오늘 아버지랑 병원에 갔다 왔는데, 어제였나 오늘이었나 조금 헷갈리네요. "
    "그래도 아버지가 웃으셔서 마음이 놓였습니다."
)
_CLEANED = (
    "오늘 아버지와 병원에 다녀온 일을 이야기했다. "
    "사용자는 그 일이 어제였는지 오늘이었는지 헷갈린다고 말했다. "
    "아버지가 웃어서 마음이 놓였다고 말했다."
)
_SEGMENTS = [
    {"start_time": 0.0, "end_time": 4.2, "speaker": "speaker_1",
     "text": "오늘 아버지랑 병원에 갔다 왔는데", "confidence": 0.91},
    {"start_time": 4.3, "end_time": 8.5, "speaker": "speaker_1",
     "text": "어제였나 오늘이었나 조금 헷갈리네요", "confidence": 0.86},
    {"start_time": 8.6, "end_time": 13.0, "speaker": "speaker_1",
     "text": "그래도 아버지가 웃으셔서 마음이 놓였습니다", "confidence": 0.93},
]


class MockSttProvider:
    name = C.PROVIDER_MOCK

    def transcribe(self, audio_path: str, language: str = "ko-KR") -> TranscriptResult:
        # audio_path는 사용하지 않는다 (고정 결과 반환).
        return TranscriptResult(
            stt_provider=C.PROVIDER_MOCK,
            language=language,
            raw_transcript=_RAW,
            cleaned_transcript=_CLEANED,
            segments=[dict(s) for s in _SEGMENTS],
            confidence_avg=0.9,
            stt_status=C.STT_SUCCESS,
            duration_sec=13.0,
        )

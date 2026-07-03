"""Mock STT Provider (지시서 9, DB명세 6.3).

실제 음성을 분석하지 않고 고정된 테스트용 STT 결과를 반환한다.
NOTE(Phase2): providers/base.py의 SttProvider Protocol을 만족하도록 리팩터,
              실제 CLOVA/RTZR/Google Provider와 교체 가능하게.
"""

from app.core import constants as C


def run(audio_id: str) -> dict:
    return {
        "stt_provider": C.PROVIDER_MOCK,
        "language": "ko-KR",
        "raw_transcript": (
            "오늘 아버지랑 병원에 갔다 왔는데, 어제였나 오늘이었나 조금 헷갈리네요. "
            "그래도 아버지가 웃으셔서 마음이 놓였습니다."
        ),
        "cleaned_transcript": (
            "오늘 아버지와 병원에 다녀온 일을 이야기했다. "
            "사용자는 그 일이 어제였는지 오늘이었는지 헷갈린다고 말했다. "
            "아버지가 웃어서 마음이 놓였다고 말했다."
        ),
        "segments": [
            {
                "start_time": 0.0,
                "end_time": 4.2,
                "speaker": "speaker_1",
                "text": "오늘 아버지랑 병원에 갔다 왔는데",
                "confidence": 0.91,
            },
            {
                "start_time": 4.3,
                "end_time": 8.5,
                "speaker": "speaker_1",
                "text": "어제였나 오늘이었나 조금 헷갈리네요",
                "confidence": 0.86,
            },
            {
                "start_time": 8.6,
                "end_time": 13.0,
                "speaker": "speaker_1",
                "text": "그래도 아버지가 웃으셔서 마음이 놓였습니다",
                "confidence": 0.93,
            },
        ],
        "confidence_avg": 0.9,
        "stt_status": C.STT_SUCCESS,
    }

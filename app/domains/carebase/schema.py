"""CareBase 상수/규칙 사전 (CAREBASE_DESIGN §1)."""

from app.core import constants as C

DOMAIN = C.DOMAIN_CAREBASE
SCHEMA_VERSION = C.SCHEMA_VERSION_CAREBASE_V1
SAFETY_NOTICE = "이 결과는 진단이 아니라 사용자 자기기록 기반 참고 신호입니다."

# missing_fields 판정 대상 (DB명세 8.3)
REQUIRED_FIELDS = ["memory_summary", "people", "places", "time_reference", "emotion"]

# evidence 생성 대상 필드 (DB명세 9장)
EVIDENCE_FIELDS = ["people", "places", "time_reference", "emotion", "risk_signal_candidates"]

# ── 규칙 사전 (DB명세 8.2) ──
PEOPLE_LEXICON = ["아버지", "어머니", "할머니", "할아버지", "가족", "친구"]
PLACES_LEXICON = ["병원", "집", "학교", "회사", "공원", "시장", "교회"]

# 감정: 트리거 어간 → 라벨
EMOTION_RULES = [
    ("마음이 놓였", "안도"),
    ("걱정", "걱정"),
    ("기뻤", "기쁨"),
    ("슬펐", "슬픔"),
    ("무서웠", "불안"),
]

# emotion 라벨 → 원문 evidence 트리거 (evidence_mapper와 정렬)
EMOTION_EVIDENCE_TRIGGER = {
    "안도": "마음이 놓였",
    "걱정": "걱정",
    "기쁨": "기뻤",
    "슬픔": "슬펐",
    "불안": "무서웠",
}

# 시간 혼동 표현 (time_reference + TIME_CONFUSION 둘 다 트리거)
TIME_CONFUSION_PHRASES = ["어제였나 오늘이었나", "오늘인지 어제인지", "언제였는지"]

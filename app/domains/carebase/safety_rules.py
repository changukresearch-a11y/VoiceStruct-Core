"""안전 표현 검사/치환 (CAREBASE_DESIGN §3, DB명세 10장).

금지 표현이 부적절한 문맥에 있으면 안전 표현으로 치환.
"진단이 아니라..." 같은 허용 문맥은 보존한다.
run + patch 두 시점 모두 적용 (DB명세 13.5).
"""

from app.core import json_utils
from app.domains.carebase.schema import SAFETY_NOTICE

# 치환 테이블 (DB명세 10.4) — 긴 표현 먼저
FORBIDDEN_SUBSTITUTIONS = [
    ("치매 의심", "표현 변화 후보"),
    ("인지저하 판정", "참고 신호 후보"),
    ("인지저하", "참고 신호 후보"),
    ("질병 진단", "진단이 아닌 참고 기록"),
    ("위험 등급", "확인 필요 수준"),
    ("의학적 조언", "보호자 확인 참고"),
    ("치매", "표현 변화 후보"),
]

# 허용 고지문 (이 문맥 안의 표현은 치환하지 않음)
ALLOWED_CONTEXTS = [
    "진단이 아니라 사용자 자기기록",
    "진단이 아니라",
    "진단이 아닌",
]


def _replace_except_allowed(text: str, forbidden: str, safe: str) -> str:
    protected: list[tuple[str, str]] = []
    for i, ctx in enumerate(ALLOWED_CONTEXTS):
        if forbidden in ctx and ctx in text:
            token = f"__SAFE_{i}__"
            text = text.replace(ctx, token)
            protected.append((token, ctx))
    text = text.replace(forbidden, safe)
    for token, ctx in protected:
        text = text.replace(token, ctx)
    return text


def apply(draft: dict) -> dict:
    text = json_utils.dumps(draft)
    for forbidden, safe in FORBIDDEN_SUBSTITUTIONS:
        if forbidden in text:
            text = _replace_except_allowed(text, forbidden, safe)
    result = json_utils.loads(text)
    # 최종 방어선: safety_notice 항상 존재 보장
    result["safety_notice"] = SAFETY_NOTICE
    return result

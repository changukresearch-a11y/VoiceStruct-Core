"""
이벤트 온톨로지 — 공시·뉴스가 공유하는 단일 event_type 목록 (단일 진실원천).

기존엔 공시/뉴스 스키마가 각자 Literal을 정의해 드리프트 위험이 있었다.
명세(인터페이스명세_정보분석→Strategist.md §10)의 통일 11종으로 합쳐,
두 스키마와 Strategist 어댑터·백테스트 집계가 모두 같은 라벨을 본다.
"""
from __future__ import annotations

from typing import Literal

# 통일 event_type (11 + other). 과세분화 금지(표본 부족→백테스트 무의미).
EventType = Literal[
    "earnings",            # 실적 발표
    "guidance_change",     # 가이던스 상/하향
    "ma",                  # M&A (인수·합병·피인수)
    "capital_raise",       # 증자·신주·전환사채 (희석)
    "buyback",             # 자사주매입·자사주 소각 (capital_raise의 반대·주주환원)
    "management_change",   # 임원·이사 변경
    "insider_trade",       # 내부자 거래 (Form 4)
    "product_deal",        # 제품 출시·대형 계약
    "analyst_rating",      # 애널리스트 등급 조정
    "regulation_legal",    # 규제·소송·조사
    "delisting_halt",      # 상장폐지·거래정지 (하드리스크 트리거)
    "other",
]

EVENT_TYPES: list[str] = list(EventType.__args__)  # 런타임 목록/검증용

# 기존(구) 라벨 → 통일 라벨 매핑 (하위호환·정규화)
_EVENT_ALIAS = {
    "material_agreement": "product_deal",   # 공시 구 라벨
    "product": "product_deal",              # 뉴스 구 라벨
    "share_repurchase": "buyback",          # 자사주매입 표기 흔들림 흡수
    "repurchase": "buyback",
    # 배당(dividend·special_dividend)은 buyback과 별개 이벤트라 매핑하지 않음(→other 유지).
}


def norm_event(event_type: str | None) -> str:
    """임의 라벨을 통일 목록으로 정규화. 미등록은 'other'."""
    if not event_type:
        return "other"
    et = _EVENT_ALIAS.get(event_type, event_type)
    return et if et in EVENT_TYPES else "other"

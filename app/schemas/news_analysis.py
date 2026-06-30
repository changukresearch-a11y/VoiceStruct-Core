"""
뉴스 분석 LLM 출력 스키마 (공시 DisclosureSignal과 별도).

뉴스는 공시와 달리 출처 신뢰도·사실/추측 구분이 핵심이라 전용 필드를 둔다.
공통 배관(decision/storage)과는 event_type·sentiment·trade_permission 등
공유 가능한 필드명을 맞춰 둔다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 뉴스 이벤트 온톨로지 (MVP 8종, 공시와 의미축은 비슷하되 뉴스 성격 반영)
NewsEventType = Literal[
    "earnings",            # 실적 관련 보도
    "guidance_change",     # 가이던스 상/하향 보도
    "ma",                  # M&A (확정/루머 포함 — is_confirmed로 구분)
    "analyst_rating",      # 애널리스트 상/하향
    "product",             # 제품/계약 발표
    "regulation_legal",    # 규제·소송·조사
    "management_change",   # 임원 변경
    "other",
]

Sentiment = Literal["positive", "negative", "neutral", "mixed"]

TradePermission = Literal[
    "TRADE_ELIGIBLE", "TRADE_ELIGIBLE_SMALL_SIZE", "WATCH_ONLY",
    "BLOCK_BUY", "RISK_REDUCE", "BLOCK_ALL",
]

CertaintyLevel = Literal["High", "Medium", "Low"]


class NewsSignal(BaseModel):
    """뉴스 1건(또는 클러스터)에 대한 LLM 구조화 분석 결과."""

    # ── 추론 강제 (공시와 동일 사상) ──
    reasoning: str = Field(..., description="[CoT] 헤드라인 핵심을 단계적으로 추론.")
    certainty_level: CertaintyLevel = Field(
        ..., description="단정적 보도(High) vs 모호/추측(Low).")

    # ── 핵심 신호 ──
    event_type: NewsEventType
    sentiment: Sentiment
    importance: int = Field(..., ge=0, le=10, description="1~5일 주가 영향 중요도.")
    risk_score: float = Field(..., ge=0, le=10)

    # ── 뉴스 전용: 신뢰도·사실성 ──
    is_confirmed: bool = Field(
        ..., description="확정 사실(발표/공시)인가? '~알려져/전망/소문'이면 False.")
    source_trust: float = Field(
        ..., ge=0, le=1,
        description="출처 신뢰도 0~1. 출처 정책 등급과 본문 톤을 함께 반영.")
    theme: list[str] = Field(default_factory=list, description="테마/섹터 태그.")

    # ── 매매 연결 ──
    hard_risk_flag: bool = False
    trade_permission: TradePermission = Field(
        ..., description="매매 권한 1차 제안. 미확인 뉴스/소셜 단독은 보수적으로.")

    reason: str = Field(..., description="한 줄 핵심 근거.")
    evidence_quotes: list[str] = Field(default_factory=list)

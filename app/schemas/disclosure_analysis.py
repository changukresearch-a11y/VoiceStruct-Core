"""
공시 분석 LLM 출력 스키마 (Walking Skeleton 핵심).

Pydantic AI의 output_type으로 사용되어, LLM이 자유 텍스트가 아니라
검증된 구조화 객체만 반환하도록 강제한다.

설계 근거(메모리):
- V1(스키마 추론강제): reasoning(CoT) + certainty_level 필드로 사고 강제.
  단 devil's advocate는 MVP에서 제외(별도 Risk Critic 패스로 Phase2).
- MVP 컷라인: event_type은 6~8종으로만 시작(과세분화 금지).
- Trade Permission 6단계 통일(BLOCK_ALL 포함).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.common.ontology import EventType

# 공시/뉴스 공유 통일 온톨로지 사용 (app/common/ontology.py, 명세 §10).
DisclosureEventType = EventType   # 하위호환 별칭

Sentiment = Literal["positive", "negative", "neutral", "mixed"]

# 매매 권한 6단계 (event-pipeline + disclosure-pipeline 통일)
TradePermission = Literal[
    "TRADE_ELIGIBLE",             # 매수 후보 (조건 충족 시)
    "TRADE_ELIGIBLE_SMALL_SIZE",  # 소액 진입만
    "WATCH_ONLY",                 # 관찰만, 매수 금지
    "BLOCK_BUY",                  # 신규 매수 차단
    "RISK_REDUCE",                # 보유 축소 검토
    "BLOCK_ALL",                  # 매수·보유 모두 위험
]

CertaintyLevel = Literal["High", "Medium", "Low"]


class DisclosureSignal(BaseModel):
    """공시 1건에 대한 LLM 구조화 분석 결과."""

    # ── 추론 강제 (V1) ──
    reasoning: str = Field(
        ...,
        description="[CoT] 공시 핵심 팩트를 순차·논리적으로 추론한 과정. "
                    "결론 전에 근거부터 단계적으로 서술.",
    )
    certainty_level: CertaintyLevel = Field(
        ...,
        description="[모호성 탐지] 단정적 사실 공시인지(High), "
                    "해석 여지가 큰 모호한 공시인지(Low) 분류.",
    )

    # ── 핵심 신호 ──
    event_type: DisclosureEventType = Field(
        ..., description="공시 이벤트 유형 (8종 중 하나).")
    sentiment: Sentiment = Field(
        ..., description="주가에 미칠 방향성.")
    importance: int = Field(
        ..., ge=0, le=10,
        description="1~5일 스윙 관점의 주가 영향 중요도 (0~10). "
                    "거래정지·상폐=10, 대형 M&A·실적쇼크=8~9, 일상보고=1~2.")
    risk_score: float = Field(
        ..., ge=0, le=10,
        description="하방·위험 점수 (0~10). 회계문제·희석·상폐 위험일수록 높음.")

    # ── 매매 연결 ──
    hard_risk_flag: bool = Field(
        False,
        description="LLM 판단과 무관하게 매수 차단해야 하는 위험 여부. "
                    "보통 코드 하드룰이 설정하므로 LLM은 기본 False.")
    trade_permission: TradePermission = Field(
        ...,
        description="매매 권한 1차 제안. 단 최종 권한은 코드 정책·시장반응이 "
                    "재결정하므로 보수적으로(확신 없으면 WATCH_ONLY).")

    # ── 근거 ──
    reason: str = Field(
        ...,
        description="한 줄 핵심 근거. 가능하면 수치(프리미엄%·EPS·증자규모 등) 포함.")
    evidence_quotes: list[str] = Field(
        default_factory=list,
        description="판단 근거가 된 공시 원문의 짧은 인용 (환각 방지용).")

    # ── 전문 요약·키워드·판정 ──
    summary: str = Field(
        "",
        description="공시 전문을 3~4줄로 요약. 핵심 사건·수치·맥락을 사람이 읽기 쉽게.")
    keywords: list[str] = Field(
        default_factory=list,
        description="핵심 키워드 5개(종목·이벤트·수치 등 검색/태깅용 단어).")
    verdict: str = Field(
        "",
        description="검증 결과 한 문장. '호재'/'악재'/'중립' 판단을 명시하고 근거 요지를 "
                    "덧붙여 결론 짓는다. 예: '호재 — 대형 현금 인수로 단기 상승 기대(신뢰 높음).'")

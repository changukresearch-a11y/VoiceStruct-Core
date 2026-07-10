"""
뉴스 분석 LLM 출력 스키마 (공시 DisclosureSignal과 별도).

뉴스는 공시와 달리 출처 신뢰도·사실/추측 구분이 핵심이라 전용 필드를 둔다.
공통 배관(decision/storage)과는 event_type·sentiment·trade_permission 등
공유 가능한 필드명을 맞춰 둔다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.common.ontology import EventType

# 공시/뉴스 공유 통일 온톨로지 사용 (app/common/ontology.py, 명세 §10).
NewsEventType = EventType   # 하위호환 별칭

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

    # ── 전문 요약·키워드·판정 ──
    summary: str = Field(
        "", description="뉴스 전문(헤드라인+본문)을 3~4줄로 요약.")
    keywords: list[str] = Field(
        default_factory=list, description="핵심 키워드 5개(검색/태깅용).")
    verdict: str = Field(
        "", description="검증 결과 한 문장. '호재'/'악재'/'중립' 판단을 명시하고 "
                        "확정/추측 여부와 근거 요지를 덧붙여 결론.")


class NewsOverview(BaseModel):
    """한 종목의 여러 기사를 종합한 배치 요약(전략가 전달용). LLM 합성.

    개별 기사(대표 1건)가 아니라 오늘 수집된 기사 묶음 전체를 대표한다.
    build_news_bundle 바깥에서 계산해 bundle.summary/keywords를 덮어쓴다(순수성 유지).
    """
    summary: str = Field(
        ..., description="기사 묶음 전체를 3~4문장으로 종합. 포함된 사건 유형들(예: 인수·소송·"
                         "실적)을 밝히고 종합 방향(bullish/bearish/mixed)을 명시. 영어로.")
    keywords: list[str] = Field(
        default_factory=list, description="묶음 전체를 대표하는 핵심 키워드 5개. 영어로.")

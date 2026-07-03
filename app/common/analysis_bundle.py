"""
정보분석(공시·뉴스) → Strategist 인터페이스 계약.

팀 회의 피드백(2026-07-02) 반영:
  - 공시·뉴스 결과를 **완전 별개 2객체**로 분리 (DisclosureBundle / NewsBundle).
    (기존: 종목당 1개 AnalysisBundle로 합치고 net_sentiment로 합산 → 폐기)
  - 모든 점수를 **0~1 소수점으로 통일** (importance·risk_score·confidence·source_trust).
    방향(호재/악재)은 점수 부호가 아니라 sentiment 라벨로만 표현.
    → 강도는 importance(0~1) 하나로. 기존 score(방향×강도)는 importance와 중복이라 폐기.
  - 종목 **회사명(company_name)·카테고리(category)** 필드 추가.
    company_name = 공시 collector가 SEC에서 채움, category = 스크리닝 에이전트가 전달.
  - Strategist가 두 소스를 직접 결합 (우리는 합산하지 않음).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.common.ontology import norm_event  # 공유 온톨로지(단일 진실원천)

_CERTAINTY = {"High": 0.9, "Medium": 0.6, "Low": 0.3}
_GRADE_SCORE = {"ALLOW": 1.0, "GRAY": 0.6, "WATCH_ONLY": 0.3, "BLOCK": 0.0}
_BLOCK = {"BLOCK_ALL", "BLOCK_BUY"}


def _n10(v: float | int | None) -> float:
    """0~10 척도를 0~1로 정규화 (소수점 통일)."""
    return round(max(0.0, min(10.0, float(v or 0))) / 10.0, 2)


def _sign(sentiment: str | None) -> int:
    return {"positive": 1, "negative": -1}.get(sentiment or "", 0)


def _senti_score(signed: float) -> float:
    """방향×강도(-1~+1)를 0~1로. 0=강악재·0.5=중립·1=강호재. mixed/neutral=0.5."""
    return round(0.5 + 0.5 * max(-1.0, min(1.0, signed)), 2)


def _head(ticker: str, company: str | None, category: str | None,
          kind: str, as_of: str) -> str:
    h = f"[{ticker}"
    if company:
        h += f" · {company}"
    if category:
        h += f" · {category}"
    return h + f"] {kind} as_of {as_of}"


# ── 공시 결과 (단독) ─────────────────────────────────────

class DisclosureBundle(BaseModel):
    """공시 분석 결과 — 종목당 1개, 뉴스와 완전 분리."""
    # 종목 식별
    ticker: str
    company_name: str | None = None
    category: str | None = None          # 스크리닝 에이전트가 전달
    as_of: str
    has_signal: int = 0                   # 0/1 (신호 유무)
    # 공시 신호 (점수 전부 0~1)
    event_type: str = "other"
    sentiment: str = "neutral"           # 방향 라벨(sentiment_score에서 파생)
    sentiment_score: float = 0.5         # 0~1: 0=강악재·0.5=중립·1=강호재
    importance: float = 0.0              # 0~1 (강도·중요도, 방향 뺀 별도 축)
    risk_score: float = 0.0              # 0~1
    confidence: float = 0.0              # 0~1
    confirmed_score: float = 0.0         # 0~1 (확정도. 공시=1.0 도장 찍힌 사실)
    # 안전장치
    hard_block: int = 0                   # 0/1 (안전장치 override)
    hard_block_reason: str | None = None
    # 근거
    reason: str = ""
    ref: str = ""

    def to_prompt(self) -> str:
        head = _head(self.ticker, self.company_name, self.category, "공시", self.as_of)
        if not self.has_signal:
            return head + f"\n 공시: 신호 없음 · hard_block={self.hard_block}"
        lines = [head, (
            f" 공시: {self.event_type} / {self.sentiment}({self.sentiment_score}) "
            f"중요도{self.importance} 위험{self.risk_score} conf{self.confidence} "
            f"확정{self.confirmed_score}")]
        if self.reason:
            lines.append(f'       "{self.reason}"')
        lines.append(
            f" 종합: hard_block={self.hard_block}"
            + (f" ({self.hard_block_reason})" if self.hard_block else ""))
        return "\n".join(lines)


# ── 뉴스 결과 (단독) ─────────────────────────────────────

class NewsBundle(BaseModel):
    """뉴스 분석 결과 — 종목당 1개, 공시와 완전 분리."""
    ticker: str
    company_name: str | None = None
    category: str | None = None
    as_of: str
    has_signal: int = 0                   # 0/1 (신호 유무)
    # 건수
    news_count: int = 0
    news_confirmed: int = 0
    news_rumor: int = 0
    # 뉴스 대표 신호 (0~1)
    event_type: str = "other"
    sentiment: str = "neutral"           # 방향 라벨(sentiment_score에서 파생)
    sentiment_score: float = 0.5         # 0~1: 0=강악재·0.5=중립·1=강호재
    importance: float = 0.0              # 0~1 (강도, 신뢰가중)
    peak_importance: float = 0.0         # 0~1 (집계 전 최고 잠재)
    risk_score: float = 0.0              # 0~1
    confidence: float = 0.0              # 0~1
    source_trust: float = 0.0            # 0~1 (뉴스 전용, LLM 판단)
    grade_score: float = 0.0             # 0~1 (출처 정책등급: ALLOW1·GRAY.6·WATCH.3·BLOCK0)
    confirmed_score: float = 0.0         # 0~1 (확정 비율 = 확정건수/전체)
    # 안전장치
    hard_block: int = 0                   # 0/1 (안전장치 override)
    hard_block_reason: str | None = None
    # 근거
    top_evidence: list[str] = Field(default_factory=list)
    reason: str = ""
    ref: str = ""

    def to_prompt(self) -> str:
        head = _head(self.ticker, self.company_name, self.category, "뉴스", self.as_of)
        if not self.has_signal:
            return head + f"\n 뉴스: {self.news_count}건 · 신호 없음"
        peak = (f" [최고imp{self.peak_importance}·저신뢰]"
                if self.peak_importance > self.importance else "")
        lines = [head, (
            f" 뉴스: {self.news_count}건(확정{self.news_confirmed}·"
            f"루머{self.news_rumor}) → {self.sentiment}({self.sentiment_score}) "
            f"중요도{self.importance} 신뢰{self.source_trust} 등급{self.grade_score} "
            f"conf{self.confidence}{peak}")]
        for ev in self.top_evidence:
            lines.append(f'       "{ev}"')
        lines.append(
            f" 종합: hard_block={self.hard_block}"
            + (f" ({self.hard_block_reason})" if self.hard_block else ""))
        return "\n".join(lines)


# ── 빌더 ────────────────────────────────────────────────

def build_disclosure_bundle(ticker: str, as_of: str, disclosure_result: Any = None,
                            company_name: str | None = None,
                            category: str | None = None) -> DisclosureBundle:
    b = DisclosureBundle(ticker=ticker.upper(), as_of=as_of,
                         company_name=company_name, category=category)
    if disclosure_result is None:
        return b
    b.company_name = company_name or getattr(
        disclosure_result.item, "company_name", None)
    if getattr(disclosure_result, "final_permission", None) in _BLOCK:
        b.hard_block = 1
        b.hard_block_reason = getattr(disclosure_result, "final_reason", None)

    sig = getattr(disclosure_result, "signal", None)
    if sig is None:
        return b
    conf = _CERTAINTY.get(getattr(sig, "certainty_level", None), 0.5)
    meta = getattr(disclosure_result.item, "meta", {}) or {}
    b.has_signal = 1
    b.confirmed_score = 1.0              # 공시 = 법적 의무 제출 = 확정 사실
    b.event_type = norm_event(getattr(sig, "event_type", None))
    b.sentiment = getattr(sig, "sentiment", None) or "neutral"
    b.importance = _n10(getattr(sig, "importance", 0))
    b.sentiment_score = _senti_score(_sign(b.sentiment) * b.importance)
    b.risk_score = _n10(getattr(sig, "risk_score", 0))
    b.confidence = round(conf, 2)
    b.reason = getattr(sig, "reason", "") or ""
    b.ref = meta.get("accession_no") or getattr(
        disclosure_result.item, "url", "") or ""
    return b


def _news_conf(sig: Any) -> float:
    c = _CERTAINTY.get(getattr(sig, "certainty_level", None), 0.5)
    c *= 1.0 if getattr(sig, "is_confirmed", False) else 0.5
    c *= getattr(sig, "source_trust", 1.0) or 1.0
    return max(0.0, min(1.0, c))


def build_news_bundle(ticker: str, as_of: str, news_results: list | None = None,
                      company_name: str | None = None,
                      category: str | None = None) -> NewsBundle:
    b = NewsBundle(ticker=ticker.upper(), as_of=as_of,
                   company_name=company_name, category=category)
    results = news_results or []

    # hard_block — 어느 뉴스든 BLOCK류면 발동
    for r in results:
        if getattr(r, "final_permission", None) in _BLOCK:
            b.hard_block = 1
            b.hard_block_reason = b.hard_block_reason or getattr(r, "final_reason", None)

    analyzed = [r for r in results if getattr(r, "signal", None) is not None]
    if not analyzed:
        return b

    b.has_signal = 1
    confirmed = sum(1 for r in analyzed if r.signal.is_confirmed)
    b.news_confirmed = confirmed
    b.news_rumor = len(analyzed) - confirmed
    b.news_count = len(analyzed)

    weights = [_news_conf(r.signal) for r in analyzed]
    tw = sum(weights) or 1.0
    # 방향 포함 강도 (-1~+1) — 집계에만 쓰고, 최종은 방향(sentiment)/강도(importance) 분리
    signed = [_n10(r.signal.importance) * _sign(r.signal.sentiment) for r in analyzed]
    agg_signed = (min(signed) if min(signed) <= -0.7
                  else sum(s * w for s, w in zip(signed, weights)) / tw)
    b.sentiment = ("positive" if agg_signed > 0
                   else "negative" if agg_signed < 0 else "neutral")
    b.sentiment_score = _senti_score(agg_signed)      # 0~1 (방향×강도)
    b.importance = round(abs(agg_signed), 2)          # 방향 뺀 강도
    b.peak_importance = _n10(max(r.signal.importance or 0 for r in analyzed))
    b.risk_score = round(
        sum(_n10(r.signal.risk_score) * w for r, w in zip(analyzed, weights)) / tw, 2)
    b.source_trust = round(
        sum((r.signal.source_trust or 0) * w for r, w in zip(analyzed, weights)) / tw, 2)
    b.confidence = round(sum(weights) / len(weights), 2)
    # 출처 정책등급을 점수로 (ALLOW1·GRAY.6·WATCH.3·BLOCK0) — 신뢰가중 평균
    b.grade_score = round(sum(
        _GRADE_SCORE.get(getattr(r, "source_grade", None), 0.6) * w
        for r, w in zip(analyzed, weights)) / tw, 2)
    b.confirmed_score = round(confirmed / b.news_count, 2)  # 확정 비율

    rep = max(analyzed, key=lambda r: (r.signal.importance or 0))
    ordered = sorted(analyzed, key=lambda r: -(r.signal.importance or 0))
    b.event_type = norm_event(rep.signal.event_type)
    b.reason = rep.signal.reason or ""
    b.ref = getattr(rep.item, "url", "") or ""
    b.top_evidence = [
        f"{(r.item.meta.get('source') or '').strip()}: {r.item.title[:60]}"
        for r in ordered[:1]]
    return b

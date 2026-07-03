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

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.common.ontology import norm_event  # 공유 온톨로지(단일 진실원천)

_CERTAINTY = {"High": 0.9, "Medium": 0.6, "Low": 0.3}
_GRADE_SCORE = {"ALLOW": 1.0, "GRAY": 0.6, "BLOCK": 0.0}   # WATCH_ONLY 소셜 등급 제거(팀 결정)
_BLOCK = {"BLOCK_ALL", "BLOCK_BUY"}


def _n10(v: float | int | None) -> float:
    """0~10 척도를 0~1로 정규화 (소수점 통일)."""
    return round(max(0.0, min(10.0, float(v or 0))) / 10.0, 2)


def _sign(sentiment: str | None) -> int:
    return {"positive": 1, "negative": -1}.get(sentiment or "", 0)


def _senti_score(signed: float, confidence: float = 1.0) -> float:
    """방향×강도(-1~+1)를 0~1로 매핑. 0=강악재·0.5=중립·1=강호재. mixed/neutral=0.5.

    고도화(비대칭 신뢰 감쇠): **호재(+)만 confidence로 중립(0.5)쪽으로 감쇠**한다.
    근거 약한 낙관을 덜 단정해 과신·펌프에 안 휘둘리기 위함(0에 가까운 confidence
    일수록 0.5로 수렴). **악재(−)는 감쇠하지 않는다** — 안전 우선이라 경고 신호를
    흐리지 않는다("가장 보수적 채택" 사상과 일치). 강도(importance)와는 별개 축.
    """
    signed = max(-1.0, min(1.0, signed))
    if signed > 0:                                   # 호재만 신뢰 감쇠
        signed *= max(0.0, min(1.0, confidence))
    return round(0.5 + 0.5 * signed, 2)


def _now() -> str:
    """레코드 생성 시각 (UTC ISO, 초 포함) — DB 생성 날짜 성격."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fact_check_disclosure() -> str:
    """공시 = 법적 의무 제출이라 사실로 확정."""
    return "Verified — official SEC filing (legally binding fact)."


def _fact_check_news(confirmed: int, count: int, trust: float, grade: float) -> str:
    """뉴스 팩트체크 상태를 확정비율·출처신뢰·등급으로 코드 판정(LLM 불필요)."""
    ratio = confirmed / count if count else 0.0
    if ratio >= 0.5 and trust >= 0.6:
        status = "Verified"
    elif confirmed == 0 or trust < 0.4:
        status = "Unverified (rumor)"
    else:
        status = "Partially verified"
    return f"{status} — {confirmed}/{count} confirmed, trust {trust}, grade {grade}."


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
    created_at: str = ""                  # 레코드 생성 시각(초 포함, DB 생성일 성격)
    has_signal: int = 0                   # 0/1 (신호 유무)
    # 공시 원문 식별 (전달용)
    filing_title: str = ""                # 공시 제목
    filing_no: str = ""                   # 공시 번호(accession)
    filed_at: str = ""                    # 업로드 일시(초 포함, acceptanceDateTime 우선)
    # 공시 신호 (점수 전부 0~1)
    event_type: str = "other"
    sentiment: str = "neutral"           # 방향 라벨(sentiment_score에서 파생)
    sentiment_score: float = 0.5         # 0~1: 0=강악재·0.5=중립·1=강호재
    importance: float = 0.0              # 0~1 (강도·중요도, 방향 뺀 별도 축)
    risk_score: float = 0.0              # 0~1
    confidence: float = 0.0              # 0~1
    confirmed_score: float = 0.0         # 0~1 (확정도. 공시=1.0 도장 찍힌 사실)
    fact_check: str = ""                  # 팩트체크 상태 한 문장(코드 판정)
    # 안전장치
    hard_block: int = 0                   # 0/1 (안전장치 override)
    hard_block_reason: str | None = None
    # 근거 · 전문 요약
    reason: str = ""                      # 한 줄 근거
    verdict: str = ""                     # 검증 결과 한 문장(호재/악재 판단)
    summary: str = ""                     # 공시 전문 3~4줄 요약
    keywords: list[str] = Field(default_factory=list)   # 핵심 키워드 5개
    ref: str = ""

    def to_prompt(self) -> str:
        head = _head(self.ticker, self.company_name, self.category, "Disclosure", self.as_of)
        filing = (f'       Filing: "{self.filing_title}" · No {self.filing_no} '
                  f"· filed {self.filed_at}"
                  if (self.filing_no or self.filing_title) else "")
        if not self.has_signal:
            out = head + f"\n Disclosure: no signal · hard_block={self.hard_block}"
            return out + (f"\n{filing}" if filing else "")
        lines = [head, (
            f" Disclosure: {self.event_type} / {self.sentiment}({self.sentiment_score}) "
            f"imp{self.importance} risk{self.risk_score} conf{self.confidence} "
            f"confirmed{self.confirmed_score}")]
        if filing:
            lines.append(filing)
        if self.fact_check:
            lines.append(f"       Fact-check: {self.fact_check}")
        if self.verdict:
            lines.append(f"       Verdict: {self.verdict}")
        if self.summary:
            lines.append(f"       Summary: {' '.join(self.summary.split())}")
        if self.keywords:
            lines.append(f"       Keywords: {', '.join(self.keywords)}")
        if self.reason:
            lines.append(f'       Reason: "{self.reason}"')
        lines.append(
            f" Overall: hard_block={self.hard_block}"
            + (f" ({self.hard_block_reason})" if self.hard_block else "")
            + (f" · generated {self.created_at}" if self.created_at else ""))
        return "\n".join(lines)


# ── 뉴스 결과 (단독) ─────────────────────────────────────

class NewsBundle(BaseModel):
    """뉴스 분석 결과 — 종목당 1개, 공시와 완전 분리."""
    ticker: str
    company_name: str | None = None
    category: str | None = None
    as_of: str
    created_at: str = ""                  # 레코드 생성 시각(초 포함, DB 생성일 성격)
    has_signal: int = 0                   # 0/1 (신호 유무)
    # 뉴스 원문 식별 (대표 기사, 전달용)
    news_title: str = ""                  # 뉴스 제목
    source: str = ""                      # 출처 언론사
    published_at: str = ""                # 업로드 일시(초 포함)
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
    grade_score: float = 0.0             # 0~1 (출처 정책등급: ALLOW1·GRAY.6·BLOCK0)
    confirmed_score: float = 0.0         # 0~1 (확정 비율 = 확정건수/전체)
    fact_check: str = ""                  # 팩트체크 상태 한 문장(코드 판정)
    # 안전장치
    hard_block: int = 0                   # 0/1 (안전장치 override)
    hard_block_reason: str | None = None
    # 근거 · 전문 요약
    top_evidence: list[str] = Field(default_factory=list)
    reason: str = ""                      # 한 줄 근거(대표 기사)
    verdict: str = ""                     # 검증 결과 한 문장(호재/악재 판단, 대표 기사)
    summary: str = ""                     # 뉴스 전문 3~4줄 요약(대표 기사)
    keywords: list[str] = Field(default_factory=list)   # 핵심 키워드 5개
    ref: str = ""

    def to_prompt(self) -> str:
        head = _head(self.ticker, self.company_name, self.category, "News", self.as_of)
        if not self.has_signal:
            return head + f"\n News: {self.news_count} items · no signal"
        peak = (f" [peak imp{self.peak_importance}·low-conf]"
                if self.peak_importance > self.importance else "")
        lines = [head, (
            f" News: {self.news_count} items (confirmed{self.news_confirmed}·"
            f"rumor{self.news_rumor}) → {self.sentiment}({self.sentiment_score}) "
            f"imp{self.importance} trust{self.source_trust} grade{self.grade_score} "
            f"conf{self.confidence}{peak}")]
        if self.source or self.published_at:
            lines.append(f"       Source: {self.source} · published {self.published_at}")
        if self.fact_check:
            lines.append(f"       Fact-check: {self.fact_check}")
        if self.verdict:
            lines.append(f"       Verdict: {self.verdict}")
        if self.summary:
            lines.append(f"       Summary: {' '.join(self.summary.split())}")
        if self.keywords:
            lines.append(f"       Keywords: {', '.join(self.keywords)}")
        for ev in self.top_evidence:
            lines.append(f'       Evidence: "{ev}"')
        lines.append(
            f" Overall: hard_block={self.hard_block}"
            + (f" ({self.hard_block_reason})" if self.hard_block else "")
            + (f" · generated {self.created_at}" if self.created_at else ""))
        return "\n".join(lines)


# ── 빌더 ────────────────────────────────────────────────

def build_disclosure_bundle(ticker: str, as_of: str, disclosure_result: Any = None,
                            company_name: str | None = None,
                            category: str | None = None) -> DisclosureBundle:
    b = DisclosureBundle(ticker=ticker.upper(), as_of=as_of,
                         company_name=company_name, category=category)
    b.created_at = _now()
    if disclosure_result is None:
        return b
    b.company_name = company_name or getattr(
        disclosure_result.item, "company_name", None)
    # 공시 원문 식별 (신호 유무와 무관하게 전달)
    meta = getattr(disclosure_result.item, "meta", {}) or {}
    b.filing_title = getattr(disclosure_result.item, "title", "") or ""
    b.filing_no = meta.get("accession_no") or ""
    b.filed_at = meta.get("accepted_at") or meta.get("filed_at") or ""
    if getattr(disclosure_result, "final_permission", None) in _BLOCK:
        b.hard_block = 1
        b.hard_block_reason = getattr(disclosure_result, "final_reason", None)

    sig = getattr(disclosure_result, "signal", None)
    if sig is None:
        return b
    conf = _CERTAINTY.get(getattr(sig, "certainty_level", None), 0.5)
    b.has_signal = 1
    b.confirmed_score = 1.0              # 공시 = 법적 의무 제출 = 확정 사실
    b.fact_check = _fact_check_disclosure()
    b.event_type = norm_event(getattr(sig, "event_type", None))
    b.sentiment = getattr(sig, "sentiment", None) or "neutral"
    b.importance = _n10(getattr(sig, "importance", 0))
    b.confidence = round(conf, 2)
    # 방향점수: 호재는 confidence(certainty_level)로 감쇠. 공시는 대개 High(0.9)라
    # 거의 안 눌리지만, 모호(Low)한 호재 공시는 방향을 덜 단정한다.
    b.sentiment_score = _senti_score(_sign(b.sentiment) * b.importance, b.confidence)
    b.risk_score = _n10(getattr(sig, "risk_score", 0))
    b.reason = getattr(sig, "reason", "") or ""
    b.verdict = getattr(sig, "verdict", "") or ""
    b.summary = getattr(sig, "summary", "") or ""
    b.keywords = list(getattr(sig, "keywords", []) or [])
    b.ref = meta.get("accession_no") or getattr(
        disclosure_result.item, "url", "") or ""
    return b


def _news_conf(sig: Any) -> float:
    c = _CERTAINTY.get(getattr(sig, "certainty_level", None), 0.5)
    c *= 1.0 if getattr(sig, "is_confirmed", False) else 0.5
    st = getattr(sig, "source_trust", None)
    c *= st if st is not None else 1.0   # 0.0(무신뢰)을 1.0으로 오인 금지(‘or’ 버그)
    return max(0.0, min(1.0, c))


def build_news_bundle(ticker: str, as_of: str, news_results: list | None = None,
                      company_name: str | None = None,
                      category: str | None = None) -> NewsBundle:
    b = NewsBundle(ticker=ticker.upper(), as_of=as_of,
                   company_name=company_name, category=category)
    b.created_at = _now()
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

    # 기사별 신뢰도(가중치). confidence는 이 원본 가중치의 평균(저신뢰면 낮게).
    raw_weights = [_news_conf(r.signal) for r in analyzed]
    b.confidence = round(sum(raw_weights) / len(raw_weights), 2)
    # 가중평균용 가중치: 전부 0(완전 저신뢰)이면 등가중 폴백 — 강도·위험 지표가
    # 0으로 붕괴하는 것을 막는다(신뢰는 위 confidence가 이미 낮게 반영).
    weights = raw_weights if sum(raw_weights) > 1e-9 else [1.0] * len(analyzed)
    tw = sum(weights)

    mags = [_n10(r.signal.importance) for r in analyzed]       # 강도(부호 없음, 0~1)
    signed = [m * _sign(r.signal.sentiment)                    # 방향×강도(-1~+1)
              for m, r in zip(mags, analyzed)]

    # 강도(importance): 방향과 무관한 신뢰가중 평균 — 호·악재가 섞여도 상쇄되지 않아
    # 같은 강도면 방향 구성과 무관하게 항상 같은 값이 나온다(일관성).
    b.importance = round(sum(m * w for m, w in zip(mags, weights)) / tw, 2)
    b.peak_importance = max(mags)   # mags는 이미 0~1(_n10 적용됨) — 재정규화 금지

    # 방향(sentiment): 강도와 별도 집계. 강한 악재(≤ −0.7) 1건이면 보수적으로 그쪽.
    strong_neg = min(signed) <= -0.7
    agg_signed = (min(signed) if strong_neg
                  else sum(s * w for s, w in zip(signed, weights)) / tw)
    # 방향점수: 호재는 confidence로 감쇠(루머뿐이면 방향을 덜 단정), 악재는 유지
    b.sentiment_score = _senti_score(agg_signed, b.confidence)
    pos_w = sum(w for s, w in zip(signed, weights) if s > 0)
    neg_w = sum(w for s, w in zip(signed, weights) if s < 0)
    # 라벨은 최종 sentiment_score에서 파생 — 항상 같은 방향을 가리킨다(라벨↔점수 일관).
    b.sentiment = (
        "negative" if strong_neg else                          # 강한 악재 우선(보수)
        "mixed" if min(pos_w, neg_w) / tw >= 0.30 else          # 호·악재 둘 다 유의미
        "positive" if b.sentiment_score > 0.5 else
        "negative" if b.sentiment_score < 0.5 else "neutral")
    b.risk_score = round(
        sum(_n10(r.signal.risk_score) * w for r, w in zip(analyzed, weights)) / tw, 2)
    b.source_trust = round(
        sum((r.signal.source_trust or 0) * w for r, w in zip(analyzed, weights)) / tw, 2)
    # 출처 정책등급을 점수로 (ALLOW1·GRAY.6·BLOCK0, 소셜/미등록=GRAY) — 신뢰가중 평균
    b.grade_score = round(sum(
        _GRADE_SCORE.get(getattr(r, "source_grade", None), 0.6) * w
        for r, w in zip(analyzed, weights)) / tw, 2)
    b.confirmed_score = round(confirmed / b.news_count, 2)  # 확정 비율
    b.fact_check = _fact_check_news(
        confirmed, b.news_count, b.source_trust, b.grade_score)

    # 대표 신호·근거 선정: importance 만이 아니라 **신뢰가중(importance×confidence)**으로
    # — 시끄럽지만 저신뢰인 루머가 대표 이벤트/헤드라인이 되지 않도록(확정 위주).
    scored = sorted(zip(analyzed, weights),
                    key=lambda rw: (rw[0].signal.importance or 0) * rw[1],
                    reverse=True)
    rep = scored[0][0]
    b.event_type = norm_event(rep.signal.event_type)
    b.reason = rep.signal.reason or ""
    b.verdict = getattr(rep.signal, "verdict", "") or ""
    b.summary = getattr(rep.signal, "summary", "") or ""
    b.keywords = list(getattr(rep.signal, "keywords", []) or [])
    # 대표 기사 원문 식별 (전달용)
    b.news_title = getattr(rep.item, "title", "") or ""
    b.source = ((getattr(rep.item, "meta", {}) or {}).get("source") or "").strip()
    _pub = getattr(rep.item, "published_at", None)
    b.published_at = _pub.isoformat() if _pub else ""
    b.ref = getattr(rep.item, "url", "") or ""
    b.top_evidence = [
        f"{(r.item.meta.get('source') or '').strip()}: {r.item.title[:60]}"
        for r, _ in scored[:1]]
    return b

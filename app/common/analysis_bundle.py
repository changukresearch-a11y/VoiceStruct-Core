"""
정보분석(공시·뉴스) → Strategist 인터페이스 계약.

팀 파이프라인 명세(2026-07-06, 김지현) 반영 — 정창욱 협의 수용:
  - 공시·뉴스 결과를 **완전 별개 2객체**로 분리 (DisclosureBundle / NewsBundle).
  - 모든 점수를 **0~1 소수점으로 통일** (importance·risk_score·confidence·source_trust 등).
    방향(호재/악재)은 sentiment_score(0~1) + sentiment 라벨로 표현.
  - 전달 = **DB 테이블 스냅샷**(tb_disclosure / tb_news, PK=(ticker, collected_at)).
    Strategist가 종목별 **최신 행**을 JOIN해 읽는다. (app/storage/db.py)

명세 수용으로 원안 대비 제거된 필드:
  - 공시(24→18): company_name·category(→tb_universe JOIN)·confirmed_score(늘 1.0)·
    fact_check(상수 문장)·verdict(sentiment_score+reason 중복)·ref(filing_no 중복).
  - 뉴스(31→24): company_name·category(JOIN)·verdict(sentiment+reason 재진술) +
    루머/팩트 이진판별 4필드(news_confirmed·news_rumor·confirmed_score·fact_check,
    2026-07-08 팀 결정 — LLM 이진판별 부정확, 신뢰도는 source_trust·grade_score로).
  - 두 객체 공통: as_of→**trade_date**, created_at→**collected_at** 개명,
    reason을 sentiment_score 바로 아래로 재배치.
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
    """레코드 생성 시각 (UTC ISO, 초 포함) — 스냅샷 collected_at 성격."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _head(ticker: str, kind: str, trade_date: str) -> str:
    return f"[{ticker}] {kind} · {trade_date}"


# ── Strategist 전달용 압축 신호 (저장 상세와 분리된 계약) ──────────────
# 저장(tb_disclosure/tb_news, 상세 컬럼)과 별개로, Strategist에겐 판단에 필요한
# 핵심 필드만 JSON으로 넘긴다. 공시·뉴스는 통합하지 않고 각자(1h/5m 주기) 전달.
# 계약 명칭은 _score 접미로 통일: importance→importance_score, source_trust→trust_score.
# (내부 DB 컬럼·LLM 스키마는 그대로 두고 여기서만 매핑 — 파급 최소.)

def _summary_with_block(d: dict) -> str:
    """hard_block이면 차단 사유를 summary 앞에 붙인다(전략가가 '왜 막혔나'를 보게)."""
    summary = d.get("summary") or ""
    if d.get("hard_block") and d.get("hard_block_reason"):
        summary = f"[차단: {d['hard_block_reason']}] {summary}".strip()
    return summary


def pack_disclosure_signal(d: dict) -> dict:
    """공시 dict(번들.model_dump() 또는 DB Row) → Strategist 압축 신호."""
    has = bool(d.get("has_signal"))
    out: dict = {"has_signal": has}
    if has:
        out.update({
            "event_type": d.get("event_type"),
            "importance_score": d.get("importance"),
            "sentiment_score": d.get("sentiment_score"),
            "risk_score": d.get("risk_score"),
        })
    out["hard_block"] = bool(d.get("hard_block"))
    if has:
        out["summary"] = _summary_with_block(d)
    return out


def pack_news_signal(d: dict) -> dict:
    """뉴스 dict → Strategist 압축 신호. peak_importance 포함(강신호 희석 방지)."""
    has = bool(d.get("has_signal"))
    out: dict = {"has_signal": has}
    if has:
        out.update({
            "article_count": d.get("news_count"),
            "event_type": d.get("event_type"),
            "importance_score": d.get("importance"),
            "peak_importance": d.get("peak_importance"),
            "sentiment_score": d.get("sentiment_score"),
            "risk_score": d.get("risk_score"),
            "trust_score": d.get("source_trust"),
        })
    out["hard_block"] = bool(d.get("hard_block"))
    if has:
        out["summary"] = _summary_with_block(d)
    return out


# ── 공시 결과 (단독) ─────────────────────────────────────

class DisclosureBundle(BaseModel):
    """공시 분석 결과 — 종목당 1개 스냅샷, 뉴스와 완전 분리. 18필드(명세 수용)."""
    # 종목 식별
    ticker: str
    trade_date: str                       # 분석 기준일(FK→tb_daily_pick), 구 as_of
    collected_at: str = ""                # 스냅샷 생성 시각(초 포함, PK), 구 created_at
    has_signal: int = 0                   # 0/1 (신호 유무)
    # 공시 원문 식별 (전달용)
    filing_title: str = ""                # 공시 제목
    filing_no: str = ""                   # 공시 번호(accession) — 원문 역추적 ID
    filed_at: str = ""                    # 업로드 일시(초 포함, acceptanceDateTime 우선)
    # 공시 신호 (점수 전부 0~1)
    event_type: str = "other"
    sentiment: str = "neutral"            # 방향 라벨(sentiment_score에서 파생)
    sentiment_score: float = 0.5          # 0~1: 0=강악재·0.5=중립·1=강호재
    is_positive: bool = False             # sentiment_score > 0.5 (호재 여부 불리언 파생, 리뷰 반영)
    reason: str = ""                      # sentiment_score 근거 한 줄
    importance: float = 0.0               # 0~1 (강도·중요도, 방향 뺀 별도 축)
    risk_score: float = 0.0               # 0~1
    confidence: float = 0.0               # 0~1 (LLM 분석 확신도)
    # 안전장치
    hard_block: int = 0                   # 0/1 (매수 즉시 차단)
    hard_block_reason: str | None = None
    # 전문 요약
    summary: str = ""                     # 공시 전문 3~4줄 요약
    keywords: list[str] = Field(default_factory=list)   # 핵심 키워드 5개

    def to_prompt(self) -> str:
        head = _head(self.ticker, "Disclosure", self.trade_date)
        filing = (f'       Filing: "{self.filing_title}" · No {self.filing_no} '
                  f"· filed {self.filed_at}"
                  if (self.filing_no or self.filing_title) else "")
        if not self.has_signal:
            out = head + f"\n Disclosure: no signal · hard_block={self.hard_block}"
            return out + (f"\n{filing}" if filing else "")
        lines = [head, (
            f" Disclosure: {self.event_type} / {self.sentiment}({self.sentiment_score}) "
            f"imp{self.importance} risk{self.risk_score} conf{self.confidence}")]
        if filing:
            lines.append(filing)
        if self.reason:
            lines.append(f'       Reason: "{self.reason}"')
        if self.summary:
            lines.append(f"       Summary: {' '.join(self.summary.split())}")
        if self.keywords:
            lines.append(f"       Keywords: {', '.join(self.keywords)}")
        lines.append(
            f" Overall: hard_block={self.hard_block}"
            + (f" ({self.hard_block_reason})" if self.hard_block else "")
            + (f" · generated {self.collected_at}" if self.collected_at else ""))
        return "\n".join(lines)

    def to_strategist_signal(self) -> dict:
        """공시 압축 신호(dict). 저장 상세 18/19필드 → 판단용 핵심만."""
        return pack_disclosure_signal(self.model_dump())


# ── 뉴스 결과 (단독) ─────────────────────────────────────

class NewsBundle(BaseModel):
    """뉴스 분석 결과 — 종목당 1개 스냅샷, 공시와 완전 분리. 24+1필드(명세 최최종 2026-07-09).

    루머/팩트 이진판별 4필드(news_confirmed·news_rumor·confirmed_score·fact_check)는
    "확정이냐 루머냐를 LLM이 무 자르듯 판별하기 어렵다"는 팀 결정으로 제거. 신뢰도는
    source_trust(LLM)·grade_score(코드 도메인)·news_count·top_evidence로 커버한다.

    disclosure_ref(신설 #10): 이진판별 대신 **공식 문서 존재 여부**로 사실성 보강 —
    뉴스 대표 event_type과 같은 종목 오늘 공시가 매칭되면 그 filing_no, 없으면 None.
    매칭은 순수성 유지를 위해 build 바깥(스케줄러)에서 accumulator 기반으로 주입한다.
    """
    ticker: str
    trade_date: str                       # 분석 기준일(FK→tb_daily_pick), 구 as_of
    collected_at: str = ""                # 스냅샷 생성 시각(초 포함, PK), 구 created_at
    has_signal: int = 0                   # 0/1 (신호 유무)
    # 뉴스 원문 식별 (대표 기사, 전달용)
    news_title: str = ""                  # 대표 기사 제목
    source: str = ""                      # 대표 기사 출처 언론사
    published_at: str = ""                # 대표 기사 발행 일시(초 포함)
    # 건수
    news_count: int = 0
    # 뉴스 대표 신호 (0~1)
    event_type: str = "other"
    disclosure_ref: str | None = None     # 대표 event_type과 매칭된 오늘 공시 filing_no(없으면 None)
    sentiment: str = "neutral"            # 방향 라벨(sentiment_score에서 파생)
    sentiment_score: float = 0.5          # 0~1: 0=강악재·0.5=중립·1=강호재
    is_positive: bool = False             # sentiment_score > 0.5 (호재 여부 불리언 파생, 리뷰 반영)
    reason: str = ""                      # sentiment_score 근거 한 줄(대표 기사)
    importance: float = 0.0               # 0~1 (강도, 신뢰가중 평균)
    peak_importance: float = 0.0          # 0~1 (집계 전 최고 잠재)
    risk_score: float = 0.0               # 0~1
    confidence: float = 0.0               # 0~1 (LLM 분석 확신도)
    source_trust: float = 0.0             # 0~1 (뉴스 전용, LLM 판단·사후)
    grade_score: float = 0.0              # 0~1 (출처 정책등급·코드·사전: ALLOW1·GRAY.6·BLOCK0)
    # 안전장치
    hard_block: int = 0                   # 0/1 (매수 즉시 차단)
    hard_block_reason: str | None = None
    # 근거 · 전문 요약
    top_evidence: list[str | None] = Field(default_factory=list)  # 근거 헤드라인 정확히 3개(부족분 None)
    summary: str = ""                     # 뉴스 전문 3~4줄 요약(대표 기사)
    keywords: list[str] = Field(default_factory=list)       # 핵심 키워드 5개
    ref: str = ""                         # 대표 기사 원문 링크(공시와 달리 중복 아님)

    def to_prompt(self) -> str:
        head = _head(self.ticker, "News", self.trade_date)
        if not self.has_signal:
            return head + f"\n News: {self.news_count} items · no signal"
        peak = (f" [peak imp{self.peak_importance}·low-conf]"
                if self.peak_importance > self.importance else "")
        lines = [head, (
            f" News: {self.news_count} items → {self.sentiment}({self.sentiment_score}) "
            f"imp{self.importance} trust{self.source_trust} grade{self.grade_score} "
            f"conf{self.confidence}{peak}")]
        if self.source or self.published_at:
            lines.append(f"       Source: {self.source} · published {self.published_at}")
        if self.disclosure_ref:                      # 공식 공시로 뒷받침된 사건(사실성↑)
            lines.append(f"       ✓ 공식공시 뒷받침({self.event_type}): {self.disclosure_ref}")
        if self.reason:
            lines.append(f'       Reason: "{self.reason}"')
        if self.summary:
            lines.append(f"       Summary: {' '.join(self.summary.split())}")
        if self.keywords:
            lines.append(f"       Keywords: {', '.join(self.keywords)}")
        for ev in self.top_evidence:
            if ev:                                   # 부족분 None은 표기 생략
                lines.append(f'       Evidence: "{ev}"')
        lines.append(
            f" Overall: hard_block={self.hard_block}"
            + (f" ({self.hard_block_reason})" if self.hard_block else "")
            + (f" · generated {self.collected_at}" if self.collected_at else ""))
        return "\n".join(lines)

    def to_strategist_signal(self) -> dict:
        """뉴스 압축 신호(dict). peak_importance 포함, trust_score로 개명 노출."""
        return pack_news_signal(self.model_dump())


# ── 빌더 ────────────────────────────────────────────────

def build_disclosure_bundle(ticker: str, trade_date: str,
                            disclosure_result: Any = None) -> DisclosureBundle:
    b = DisclosureBundle(ticker=ticker.upper(), trade_date=trade_date)
    b.collected_at = _now()
    if disclosure_result is None:
        return b
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
    b.event_type = norm_event(getattr(sig, "event_type", None))
    b.sentiment = getattr(sig, "sentiment", None) or "neutral"
    b.importance = _n10(getattr(sig, "importance", 0))
    b.confidence = round(conf, 2)
    # 방향점수: 호재는 confidence(certainty_level)로 감쇠. 공시는 대개 High(0.9)라
    # 거의 안 눌리지만, 모호(Low)한 호재 공시는 방향을 덜 단정한다.
    b.sentiment_score = _senti_score(_sign(b.sentiment) * b.importance, b.confidence)
    b.is_positive = b.sentiment_score > 0.5   # 호재 불리언 파생(리뷰 반영)
    b.risk_score = _n10(getattr(sig, "risk_score", 0))
    b.reason = getattr(sig, "reason", "") or ""
    b.summary = getattr(sig, "summary", "") or ""
    b.keywords = list(getattr(sig, "keywords", []) or [])
    return b


def _news_conf(sig: Any) -> float:
    c = _CERTAINTY.get(getattr(sig, "certainty_level", None), 0.5)
    c *= 1.0 if getattr(sig, "is_confirmed", False) else 0.5
    st = getattr(sig, "source_trust", None)
    c *= st if st is not None else 1.0   # 0.0(무신뢰)을 1.0으로 오인 금지(‘or’ 버그)
    return max(0.0, min(1.0, c))


def _news_credible(r: Any) -> bool:
    """peak_importance 산정 자격 — 신뢰검증된 기사인가.
    확정 사실 or source_trust≥0.6 or 출처 정책등급 ALLOW 중 하나면 True.
    (저신뢰 매체가 자극적으로 부풀린 importance가 가짜 peak를 세우는 것 방지)
    """
    sig = getattr(r, "signal", None)
    if sig is None:
        return False
    st = getattr(sig, "source_trust", None) or 0.0
    return (bool(getattr(sig, "is_confirmed", False))
            or st >= 0.6
            or getattr(r, "source_grade", None) == "ALLOW")


def build_news_bundle(ticker: str, trade_date: str,
                      news_results: list | None = None) -> NewsBundle:
    b = NewsBundle(ticker=ticker.upper(), trade_date=trade_date)
    b.collected_at = _now()
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
    # peak_importance: '가장 센 기사 1건'이되 **신뢰검증된 기사 중에서만** 산정한다
    # (_news_credible: 확정 or source_trust≥0.6 or ALLOW). 저신뢰 매체의 자극적
    # 과장이 가짜 peak를 세우는 편향을 차단(2026-07-07). 신뢰 기사 최댓값이 평균보다
    # 클 때만 부각 — 신뢰 기사가 없으면 importance로 수렴(peak≥importance 불변식 유지,
    # low-conf 딱지도 신뢰 기반으로만 발화).
    cred_mags = [m for m, r in zip(mags, analyzed) if _news_credible(r)]
    b.peak_importance = round(max([b.importance] + cred_mags), 2)

    # 방향(sentiment): 강도와 별도 집계. 강한 악재(≤ −0.7) 1건이면 보수적으로 그쪽.
    strong_neg = min(signed) <= -0.7
    agg_signed = (min(signed) if strong_neg
                  else sum(s * w for s, w in zip(signed, weights)) / tw)
    # 방향점수: 호재는 confidence로 감쇠(루머뿐이면 방향을 덜 단정), 악재는 유지
    b.sentiment_score = _senti_score(agg_signed, b.confidence)
    b.is_positive = b.sentiment_score > 0.5   # 호재 불리언 파생(리뷰 반영)
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

    # 대표 신호·근거 선정: importance 만이 아니라 **신뢰가중(importance×confidence)**으로
    # — 시끄럽지만 저신뢰인 루머가 대표 이벤트/헤드라인이 되지 않도록(확정 위주).
    scored = sorted(zip(analyzed, weights),
                    key=lambda rw: (rw[0].signal.importance or 0) * rw[1],
                    reverse=True)
    rep = scored[0][0]
    b.event_type = norm_event(rep.signal.event_type)
    b.reason = rep.signal.reason or ""
    b.summary = getattr(rep.signal, "summary", "") or ""
    b.keywords = list(getattr(rep.signal, "keywords", []) or [])
    # 대표 기사 원문 식별 (전달용)
    b.news_title = getattr(rep.item, "title", "") or ""
    b.source = ((getattr(rep.item, "meta", {}) or {}).get("source") or "").strip()
    _pub = getattr(rep.item, "published_at", None)
    b.published_at = _pub.isoformat() if _pub else ""
    b.ref = getattr(rep.item, "url", "") or ""
    # 근거 헤드라인: 신뢰가중 상위 3개(명세 §06 "정확히 3개, 부족분 null").
    ev = [f"{(r.item.meta.get('source') or '').strip()}: {r.item.title[:60]}"
          for r, _ in scored[:3]]
    b.top_evidence = (ev + [None, None, None])[:3]   # 고정 3칸, 부족분 None
    return b

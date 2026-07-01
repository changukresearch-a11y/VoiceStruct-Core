"""
정보분석(공시·뉴스) → Strategist 인터페이스 계약.

우리 signals(DisclosureSignal/NewsSignal)를 종목당 1개 AnalysisBundle로
집계·압축한다. Strategist(LLM)는 to_prompt()의 압축 텍스트를, 코드(PM·게이트)는
타입 객체를 소비한다. (명세: 인터페이스명세_정보분석→Strategist.md)
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.common.ontology import norm_event  # 공유 온톨로지(단일 진실원천)

_CERTAINTY = {"High": 0.9, "Medium": 0.6, "Low": 0.3}
_BLOCK = {"BLOCK_ALL", "BLOCK_BUY"}


def _score(importance: int | None, sentiment: str | None) -> int:
    """방향(부호)×강도 → -10..+10."""
    imp = importance or 0
    if sentiment == "positive":
        return imp
    if sentiment == "negative":
        return -imp
    return 0


class AnalystSignal(BaseModel):
    source: Literal["disclosure", "news"]
    event_type: str
    sentiment: str
    score: int             # -10..+10 (방향×신뢰반영 강도)
    importance: int        # 0..10 (신뢰반영 — score와 같은 기준)
    peak_importance: int = 0  # 집계 전 최고 잠재 중요도 (뉴스 여러건 중 최대)
    confidence: float      # 0..1
    is_confirmed: bool
    reason: str
    ref: str = ""


class AnalysisBundle(BaseModel):
    ticker: str
    as_of: str
    disclosure: AnalystSignal | None = None
    news: AnalystSignal | None = None
    news_count: int = 0
    news_confirmed: int = 0
    news_rumor: int = 0
    net_sentiment: int = 0
    hard_block: bool = False
    hard_block_reason: str | None = None
    top_evidence: list[str] = Field(default_factory=list)

    def to_prompt(self) -> str:
        """Strategist(LLM)가 읽는 압축 텍스트."""
        lines = [f"[{self.ticker}] as_of {self.as_of}"]
        if self.disclosure:
            d = self.disclosure
            lines.append(
                f" 공시: {d.event_type} / {d.sentiment}({d.score:+d}) "
                f"중요도{d.importance} conf{d.confidence} "
                f"{'확정' if d.is_confirmed else '미확정'}")
            if d.reason:
                lines.append(f'       "{d.reason}"')
        if self.news:
            n = self.news
            # 잠재 중요도가 신뢰반영 값보다 크면(예: 실적 헤드라인이지만 저신뢰) 병기
            peak = (f" [최고imp{n.peak_importance}·저신뢰]"
                    if n.peak_importance > n.importance else "")
            lines.append(
                f" 뉴스: {self.news_count}건(확정{self.news_confirmed}·"
                f"루머{self.news_rumor}) → {n.sentiment}({n.score:+d}) "
                f"중요도{n.importance} conf{n.confidence}{peak}")
            for ev in self.top_evidence:
                lines.append(f'       "{ev}"')
        lines.append(
            f" 종합: net_sentiment {self.net_sentiment:+d} · "
            f"hard_block={str(self.hard_block).lower()}"
            + (f" ({self.hard_block_reason})" if self.hard_block else ""))
        return "\n".join(lines)


# ── 어댑터: 우리 result/signal → envelope ────────────────────────────

def from_disclosure(result: Any) -> AnalystSignal | None:
    sig = getattr(result, "signal", None)
    if sig is None:
        return None
    conf = _CERTAINTY.get(getattr(sig, "certainty_level", None), 0.5)
    meta = getattr(result.item, "meta", {}) or {}
    return AnalystSignal(
        source="disclosure",
        event_type=norm_event(getattr(sig, "event_type", None)),
        sentiment=getattr(sig, "sentiment", None) or "neutral",
        score=_score(getattr(sig, "importance", 0), getattr(sig, "sentiment", None)),
        importance=getattr(sig, "importance", 0) or 0,
        confidence=round(conf, 2),
        is_confirmed=True,   # 공시 = 법적 의무·거짓 시 처벌 = 도장 찍힌 사실
        reason=getattr(sig, "reason", "") or "",
        ref=meta.get("accession_no") or getattr(result.item, "url", "") or "",
    )


def _news_conf(sig: Any) -> float:
    c = _CERTAINTY.get(getattr(sig, "certainty_level", None), 0.5)
    c *= 1.0 if getattr(sig, "is_confirmed", False) else 0.5
    c *= getattr(sig, "source_trust", 1.0) or 1.0
    return max(0.0, min(1.0, c))


def from_news(results: list) -> tuple[AnalystSignal | None, int, int, list[str]]:
    """분석된 뉴스 여러 건 → 대표 1개로 집계. (signal, 확정수, 루머수, top근거)."""
    analyzed = [r for r in results if getattr(r, "signal", None) is not None]
    if not analyzed:
        return None, 0, 0, []
    confirmed = sum(1 for r in analyzed if r.signal.is_confirmed)
    rumor = len(analyzed) - confirmed

    weights = [_news_conf(r.signal) for r in analyzed]
    imps = [r.signal.importance or 0 for r in analyzed]
    scores = [_score(r.signal.importance, r.signal.sentiment) for r in analyzed]
    tw = sum(weights) or 1.0
    # 강한 악재(≤ -7) 있으면 보수적으로 그쪽, 아니면 신뢰가중 평균
    agg_score = min(scores) if min(scores) <= -7 else round(
        sum(s * w for s, w in zip(scores, weights)) / tw)
    # importance도 신뢰가중 평균 → score와 같은 기준(불일치 제거). peak는 별도 보존.
    agg_importance = round(sum(i * w for i, w in zip(imps, weights)) / tw)
    peak_importance = max(imps)
    agg_conf = round(sum(weights) / len(weights), 2)
    sent = "positive" if agg_score > 0 else "negative" if agg_score < 0 else "neutral"

    rep = max(analyzed, key=lambda r: (r.signal.importance or 0))
    ordered = sorted(analyzed, key=lambda r: -(r.signal.importance or 0))
    top_ev = [
        f"{(r.item.meta.get('source') or '').strip()}: {r.item.title[:60]}"
        for r in ordered[:1]]

    sig = AnalystSignal(
        source="news",
        event_type=norm_event(rep.signal.event_type),
        sentiment=sent, score=agg_score,
        importance=agg_importance, peak_importance=peak_importance,
        confidence=agg_conf,
        is_confirmed=confirmed >= rumor and confirmed > 0,
        reason=rep.signal.reason or "",
        ref=getattr(rep.item, "url", "") or "",
    )
    return sig, confirmed, rumor, top_ev


def _combine(d: AnalystSignal | None, n: AnalystSignal | None) -> int:
    vals = [(s.score, s.confidence) for s in (d, n) if s is not None]
    if not vals:
        return 0
    scores = [v[0] for v in vals]
    if min(scores) <= -7:                 # 강한 악재 우선(가장 보수적)
        return min(scores)
    tw = sum(w for _, w in vals) or 1.0
    return round(sum(s * w for s, w in vals) / tw)


def build_bundle(ticker: str, as_of: str, disclosure_result: Any = None,
                 news_results: list | None = None) -> AnalysisBundle:
    d = from_disclosure(disclosure_result) if disclosure_result else None
    n, conf, rum, top = (from_news(news_results) if news_results else (None, 0, 0, []))

    hb = False
    hbr = None
    if disclosure_result and getattr(disclosure_result, "final_permission", None) in _BLOCK:
        hb, hbr = True, getattr(disclosure_result, "final_reason", None)
    for r in (news_results or []):
        if getattr(r, "final_permission", None) in _BLOCK:
            hb = True
            hbr = hbr or getattr(r, "final_reason", None)

    return AnalysisBundle(
        ticker=ticker.upper(), as_of=as_of, disclosure=d, news=n,
        news_count=conf + rum, news_confirmed=conf, news_rumor=rum,
        net_sentiment=_combine(d, n), hard_block=hb, hard_block_reason=hbr,
        top_evidence=top)

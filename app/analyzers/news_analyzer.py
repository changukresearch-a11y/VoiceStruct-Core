"""
뉴스 LLM 분석기 (공시 disclosure_analyzer와 별도 에이전트/프롬프트/스키마).

NormalizedItem(뉴스) → NewsSignal. 출처 등급을 LLM 입력에 함께 주입한다.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.common.llm_client import build_agent
from app.common.schemas import NormalizedItem
from app.policies.source_trust_policy import classify_source
from app.schemas.news_analysis import NewsOverview, NewsSignal

_PROMPT = Path(__file__).resolve().parent / "prompts" / "news_prompt.md"
_OVERVIEW_PROMPT = Path(__file__).resolve().parent / "prompts" / "news_overview_prompt.md"


@lru_cache(maxsize=1)
def _agent():
    return build_agent(NewsSignal, _PROMPT.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _overview_agent():
    return build_agent(NewsOverview, _OVERVIEW_PROMPT.read_text(encoding="utf-8"))


def analyze(item: NormalizedItem) -> NewsSignal:
    grade = classify_source(item.url)
    user_input = (
        f"[{item.ticker}] 출처등급={grade} source={item.meta.get('source')}\n"
        f"제목: {item.title}\n본문: {item.body}"
    )
    return _agent().run_sync(user_input).output


def synthesize_overview(bundle, analyzed: list) -> NewsOverview:
    """분석 기사들 + 집계 점수를 LLM에 주어 배치 종합 요약·키워드·점수별 근거를 만든다."""
    lines = []
    for r in analyzed:
        sig = r.signal
        detail = (getattr(sig, "summary", "") or getattr(sig, "reason", "") or "").strip()
        conf = "confirmed" if getattr(sig, "is_confirmed", False) else "unconfirmed"
        lines.append(
            f"- ({sig.event_type}/{sig.sentiment}/{conf}) {r.item.title} :: {detail}")
    scores = (f"SCORES(0~1): importance={bundle.importance_score} "
              f"peak_importance={bundle.peak_importance_score} "
              f"sentiment={bundle.sentiment_score} risk={bundle.risk_score} "
              f"trust={bundle.trust_score}")
    user_input = (f"[{bundle.ticker}] {len(analyzed)} articles today:\n"
                  + "\n".join(lines) + "\n\n" + scores)
    return _overview_agent().run_sync(user_input).output


def enrich_bundle_overview(bundle, news_results: list):
    """LLM 배치 종합으로 요약·키워드·점수별 근거(_score_reason 5종)를 채운다.

    has_signal이고 분석 기사≥1이면 호출한다(근거는 1건이어도 필요). 요약·키워드
    override는 2건 이상일 때만(1건이면 대표 요약 유지). LLM 실패 시 기존값을 유지해
    견고성을 지킨다. build_news_bundle 바깥에서 돌려 그 순수성을 깨지 않는다.
    """
    if not getattr(bundle, "has_signal", 0):
        return bundle
    analyzed = [r for r in (news_results or []) if getattr(r, "signal", None) is not None]
    if not analyzed:
        return bundle
    try:
        ov = synthesize_overview(bundle, analyzed)
    except Exception:                           # 네트워크·LLM 실패 → 기존값 유지
        return bundle
    if not ov:
        return bundle
    bundle.importance_score_reason = ov.importance_reason or ""
    bundle.peak_importance_score_reason = ov.peak_importance_reason or ""
    bundle.sentiment_score_reason = ov.sentiment_reason or ""
    bundle.risk_score_reason = ov.risk_reason or ""
    bundle.trust_score_reason = ov.trust_reason or ""
    if len(analyzed) >= 2 and ov.summary:       # 묶음 종합 요약은 2건 이상일 때만 override
        bundle.summary = ov.summary
        if ov.keywords:
            bundle.keywords = list(ov.keywords)
    return bundle

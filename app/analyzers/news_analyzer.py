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


def synthesize_overview(ticker: str, analyzed: list) -> NewsOverview:
    """분석된 기사들(각 .signal)을 LLM으로 한 개의 배치 종합 요약·키워드로 합친다."""
    lines = []
    for r in analyzed:
        sig = r.signal
        detail = (getattr(sig, "summary", "") or getattr(sig, "reason", "") or "").strip()
        conf = "confirmed" if getattr(sig, "is_confirmed", False) else "unconfirmed"
        lines.append(
            f"- ({sig.event_type}/{sig.sentiment}/{conf}) {r.item.title} :: {detail}")
    user_input = f"[{ticker}] {len(analyzed)} articles today:\n" + "\n".join(lines)
    return _overview_agent().run_sync(user_input).output


def enrich_bundle_overview(bundle, news_results: list):
    """LLM 배치 종합으로 bundle.summary/keywords를 덮어쓴다(대표 1건 → 묶음 전체).

    기사 2건 이상·has_signal일 때만 호출한다(1건이면 대표=전체라 불필요).
    LLM 실패 시 기존(대표 기사) 요약을 그대로 유지해 견고성을 지킨다.
    build_news_bundle 바깥에서 돌려 그 순수성을 깨지 않는다(disclosure_ref와 동일 패턴).
    """
    if not getattr(bundle, "has_signal", 0):
        return bundle
    analyzed = [r for r in (news_results or []) if getattr(r, "signal", None) is not None]
    if len(analyzed) < 2:                       # 1건이면 대표 요약이 곧 전체
        return bundle
    try:
        ov = synthesize_overview(bundle.ticker, analyzed)
    except Exception:                           # 네트워크·LLM 실패 → 대표 요약 유지
        return bundle
    if ov and ov.summary:
        bundle.summary = ov.summary
        if ov.keywords:
            bundle.keywords = list(ov.keywords)
    return bundle

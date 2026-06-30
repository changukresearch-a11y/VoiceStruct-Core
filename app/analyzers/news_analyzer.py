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
from app.schemas.news_analysis import NewsSignal

_PROMPT = Path(__file__).resolve().parent / "prompts" / "news_prompt.md"


@lru_cache(maxsize=1)
def _agent():
    return build_agent(NewsSignal, _PROMPT.read_text(encoding="utf-8"))


def analyze(item: NormalizedItem) -> NewsSignal:
    grade = classify_source(item.url)
    user_input = (
        f"[{item.ticker}] 출처등급={grade} source={item.meta.get('source')}\n"
        f"제목: {item.title}\n본문: {item.body}"
    )
    return _agent().run_sync(user_input).output

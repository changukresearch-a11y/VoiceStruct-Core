"""
공시 LLM 분석기 (Pydantic AI).

NormalizedItem → DisclosureSignal(검증된 구조화 출력).
form_type에 따라 프롬프트를 바꾼다:
  - 8-K        → disclosure_8k_prompt.md       (이벤트 해석)
  - 10-Q/10-K  → disclosure_financial_prompt.md (XBRL 수치 해석)

LLM 호출은 LLM provider 키(OPENAI_API_KEY/ANTHROPIC_API_KEY)가 있어야 동작한다.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.common.llm_client import build_agent
from app.common.schemas import NormalizedItem
from app.schemas.disclosure_analysis import DisclosureSignal

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_PROMPT_FILES = {
    "8k": "disclosure_8k_prompt.md",
    "financial": "disclosure_financial_prompt.md",
}


@lru_cache(maxsize=2)
def _agent(kind: str):
    system_prompt = (_PROMPTS_DIR / _PROMPT_FILES[kind]).read_text(encoding="utf-8")
    return build_agent(DisclosureSignal, system_prompt)


def _kind_for(form_type: str | None) -> str:
    return "financial" if form_type in ("10-Q", "10-K") else "8k"


def analyze(item: NormalizedItem) -> DisclosureSignal:
    """공시(또는 재무수치 요약)를 LLM으로 분석해 구조화 신호를 반환."""
    form_type = item.meta.get("form_type")
    user_input = (
        f"[{item.ticker}] form={form_type} item={item.meta.get('item_no')}\n\n{item.body}"
    )
    result = _agent(_kind_for(form_type)).run_sync(user_input)
    return result.output

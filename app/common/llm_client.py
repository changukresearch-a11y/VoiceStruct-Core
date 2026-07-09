"""
LLM 클라이언트 추상화.

분석가 티어는 싼/빠른 모델(Claude Haiku), 결정 티어는 강한 모델(Claude)로
분담한다. 모델명을 한 곳에서 갈아끼울 수 있게 추상화한다.

env:
  LLM_ANALYST_MODEL  (default: anthropic:claude-haiku-4-5)
  ANTHROPIC_API_KEY
  LLM_TEMPERATURE    (default: 0 — 분석 결정론화, 리뷰 반영)
"""
from __future__ import annotations

import os
from typing import Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

DEFAULT_ANALYST_MODEL = "anthropic:claude-haiku-4-5"

# 분석 온도 0 = 같은 입력이면 항상 같은 출력(결정론적). 리뷰 반영.
# 정보분석은 '창작'이 아니라 '판정'이라 무작위성이 오히려 노이즈 → 0 고정.
# 필요 시 env LLM_TEMPERATURE로 조절(A/B·디버그용).
ANALYST_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))


def build_agent(output_type: Type[T], system_prompt: str, model: str | None = None):
    """Pydantic AI Agent 팩토리. output_type으로 구조화 출력을 강제한다.

    pydantic-ai 미설치 환경에서도 골격이 import 되도록 지연 임포트한다.
    온도는 ANALYST_TEMPERATURE(기본 0)로 고정해 재현 가능한 분석을 보장한다.
    """
    from pydantic_ai import Agent  # 지연 임포트

    model = model or os.getenv("LLM_ANALYST_MODEL", DEFAULT_ANALYST_MODEL)
    return Agent(model, output_type=output_type, system_prompt=system_prompt,
                 model_settings={"temperature": ANALYST_TEMPERATURE})

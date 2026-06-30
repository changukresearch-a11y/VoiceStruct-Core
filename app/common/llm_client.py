"""
LLM 클라이언트 추상화.

분석가 티어는 싼/빠른 모델(Claude Haiku), 결정 티어는 강한 모델(Claude)로
분담한다. 모델명을 한 곳에서 갈아끼울 수 있게 추상화한다.

env:
  LLM_ANALYST_MODEL  (default: anthropic:claude-haiku-4-5)
  ANTHROPIC_API_KEY
"""
from __future__ import annotations

import os
from typing import Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

DEFAULT_ANALYST_MODEL = "anthropic:claude-haiku-4-5"


def build_agent(output_type: Type[T], system_prompt: str, model: str | None = None):
    """Pydantic AI Agent 팩토리. output_type으로 구조화 출력을 강제한다.

    pydantic-ai 미설치 환경에서도 골격이 import 되도록 지연 임포트한다.
    """
    from pydantic_ai import Agent  # 지연 임포트

    model = model or os.getenv("LLM_ANALYST_MODEL", DEFAULT_ANALYST_MODEL)
    return Agent(model, output_type=output_type, system_prompt=system_prompt)

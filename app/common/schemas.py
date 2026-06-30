"""
공통 정규화 스키마.

공시·뉴스 등 모든 소스가 수집 직후 이 NormalizedItem 형태로 변환된다.
이후 정책필터 → LLM분석 → 시장반응 → 권한결정은 source_type으로만 분기하고
나머지 파이프라인은 공유한다. (공통 레이어 결정)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SourceType = Literal["disclosure", "news"]


class NormalizedItem(BaseModel):
    """수집된 1건(공시/뉴스)의 정규화 표현 — 파이프라인 공통 입력."""

    source_type: SourceType
    ticker: str
    company_name: str | None = None

    title: str
    body: str = Field(..., description="LLM에 넘길 본문(공시는 청킹된 Item 섹션).")
    url: str | None = None
    published_at: datetime | None = None

    # 소스별 메타데이터 (공시: form_type/item_no/cik/accession_no, 뉴스: source 등)
    meta: dict[str, Any] = Field(default_factory=dict)

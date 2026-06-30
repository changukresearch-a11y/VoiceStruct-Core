"""
8-K Item 라우터.

8-K는 Item 번호에 따라 의미가 완전히 다르므로, 본문 전체를 LLM에 넘기기 전에
Item 번호로 기본 event_type/importance/permission/hard_risk 를 부여한다.

설계 근거(메모리 disclosure-pipeline):
- 1차는 SEC 제출 메타데이터의 구조화된 Item 번호를 사용(정규식은 fallback).
- 위험 Item(3.01/4.01/2.06)은 hard_risk=true → 하드룰이 LLM보다 우선.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CONFIG = Path(__file__).resolve().parents[2] / "config" / "item_event_map.yaml"


@lru_cache(maxsize=1)
def _load_map() -> dict[str, Any]:
    with _CONFIG.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def route_item(item_no: str) -> dict[str, Any]:
    """Item 번호('2.02')로 기본 분류값을 반환. 없으면 default."""
    cfg = _load_map()
    entry = cfg.get("items", {}).get(item_no)
    if entry is None:
        entry = cfg["default"]
    return {
        "item_no": item_no,
        "event_type": entry["event_type"],
        "default_importance": entry["default_importance"],
        "default_permission": entry["default_permission"],
        "hard_risk": entry.get("hard_risk", False),
    }


# fallback: SEC 메타에 Item 번호가 없을 때 본문 헤더에서 추출
_ITEM_RE = re.compile(r"Item\s+(\d\.\d{2})", re.IGNORECASE)


def extract_item_numbers(text: str) -> list[str]:
    """본문에서 'Item X.YY' 패턴을 추출 (메타데이터 우선, 이건 fallback)."""
    return sorted(set(_ITEM_RE.findall(text)))

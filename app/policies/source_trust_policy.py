"""
뉴스 출처 정책 + 입력 키워드 필터 (LLM 호출 전 단계).

- classify_source(url) → ALLOW / GRAY / WATCH_ONLY / BLOCK
- keyword_screen(text) → (verdict, hit)  pass/whitelist/drop
  화이트리스트가 블랙리스트보다 우선(false negative 방지).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

_CFG_DIR = Path(__file__).resolve().parents[2] / "config"
_TRUST = _CFG_DIR / "news_trust_policy.yaml"
_KEYWORD = _CFG_DIR / "news_keyword_filter.yaml"

SourcePolicy = Literal["ALLOW", "GRAY", "WATCH_ONLY", "BLOCK"]


@lru_cache(maxsize=1)
def _trust_cfg() -> dict[str, Any]:
    with _TRUST.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def _keyword_cfg() -> dict[str, Any]:
    with _KEYWORD.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify_source(url: str | None) -> SourcePolicy:
    """URL 도메인으로 출처 등급 판정. 미등록 도메인은 GRAY(보수적 기본)."""
    if not url:
        return "GRAY"
    low = url.lower()
    policy = _trust_cfg()["source_policy"]
    for grade in ("ALLOW", "GRAY", "WATCH_ONLY"):
        for domain in policy.get(grade, []):
            if domain in low:
                return grade  # type: ignore[return-value]
    return "GRAY"


@dataclass
class KeywordVerdict:
    result: Literal["pass", "whitelist", "drop"]
    category: str | None = None
    keyword: str | None = None


def keyword_screen(text: str) -> KeywordVerdict:
    """입력 키워드 필터. 화이트 우선 → 블랙 → 통과."""
    low = text.lower()
    cfg = _keyword_cfg()

    for category, kws in cfg.get("whitelist", {}).items():
        for kw in kws:
            if kw in low:
                return KeywordVerdict("whitelist", category, kw)

    for category, kws in cfg.get("blacklist", {}).items():
        for kw in kws:
            if kw in low:
                return KeywordVerdict("drop", category, kw)

    return KeywordVerdict("pass")

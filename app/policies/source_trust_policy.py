"""
뉴스 출처 정책 + 입력 키워드 필터 (LLM 호출 전 단계).

- classify_source(url) → ALLOW / GRAY / BLOCK  (소셜·미등록=BLOCK, GRAY는 2급 언론 한정 — 2026-07-10)
- keyword_screen(text) → (verdict, hit)  pass/whitelist/drop
  화이트리스트가 블랙리스트보다 우선(false negative 방지).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml

_CFG_DIR = Path(__file__).resolve().parents[2] / "config"
_TRUST = _CFG_DIR / "news_trust_policy.yaml"
_KEYWORD = _CFG_DIR / "news_keyword_filter.yaml"

SourcePolicy = Literal["ALLOW", "GRAY", "BLOCK"]


@lru_cache(maxsize=1)
def _trust_cfg() -> dict[str, Any]:
    with _TRUST.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def _keyword_cfg() -> dict[str, Any]:
    with _KEYWORD.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _host_of(url: str) -> str:
    """URL에서 호스트명만 추출(소문자, 포트·계정 제거). 스킴 없으면 보정."""
    netloc = urlparse(url if "://" in url else "http://" + url).netloc.lower()
    return netloc.split("@")[-1].split(":")[0]


def classify_source(url: str | None) -> SourcePolicy:
    """URL 도메인으로 출처 등급 판정.

    GRAY는 '등록된 2급 언론사'로 한정. 소셜·포럼·미등록 도메인은 BLOCK(LLM 전 drop)
    — 팀 결정 2026-07-10. BLOCK은 명시 목록 + 기본값 양쪽에서 잡힌다.
    호스트 경계 매칭(정확일치 또는 서브도메인)이라 x.com이 netflix.com을 오탐하지 않는다.
    """
    if not url:
        return "BLOCK"
    host = _host_of(url)
    policy = _trust_cfg()["source_policy"]
    for grade in ("ALLOW", "GRAY", "BLOCK"):
        for domain in policy.get(grade, []):
            d = str(domain).lower()
            if host == d or host.endswith("." + d):
                return grade  # type: ignore[return-value]
    return "BLOCK"   # 미등록(소셜 포함) 전부 BLOCK — GRAY는 등록 2급 언론만


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

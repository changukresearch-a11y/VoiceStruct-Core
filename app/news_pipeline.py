"""
뉴스 Walking Skeleton — 한 줄 관통.

흐름:
  수집 → 출처 등급 분류 → 입력 키워드 필터(LLM 전 drop) → LLM 분석 → 최종권한 종합
        (출처=BLOCK 또는 키워드=drop 이면 LLM 호출 없이 조기 종료)

공시와 분리된 로직이지만, 최종권한(decision)·저장(storage)은 공통 배관을 재사용.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.common.schemas import NormalizedItem
from app.decision.trade_permission_policy import decide_final_permission
from app.policies.source_trust_policy import classify_source, keyword_screen


@dataclass
class NewsResult:
    item: NormalizedItem
    source_grade: str
    keyword_verdict: Any
    signal: Any = None                  # NewsSignal | None
    final_permission: str | None = None
    final_reason: str | None = None
    dropped: bool = False
    notes: list[str] = field(default_factory=list)


def run_news_pipeline(item: NormalizedItem, run_llm: bool = False) -> NewsResult:
    grade = classify_source(item.url)
    kv = keyword_screen(f"{item.title} {item.body}")
    result = NewsResult(item=item, source_grade=grade, keyword_verdict=kv)

    # 조기 종료: 출처 BLOCK 또는 키워드 drop → LLM 호출 안 함
    if grade == "BLOCK" or kv.result == "drop":
        result.dropped = True
        result.final_permission = "BLOCK_BUY" if grade == "BLOCK" else "WATCH_ONLY"
        result.final_reason = (
            f"사전필터 차단: 출처={grade}, 키워드={kv.result}/{kv.category}")
        result.notes.append("LLM 호출 전 drop (비용 절감).")
        return result

    if kv.result == "whitelist":
        result.notes.append(f"화이트리스트 우선: {kv.category}/{kv.keyword}")

    # LLM 분석
    if run_llm:
        from app.analyzers.news_analyzer import analyze
        result.signal = analyze(item)
    else:
        result.notes.append("run_llm=False → LLM 건너뜀(배선만 검증).")

    # 최종권한 (공통 배관 재사용 — 하드룰 없음, routed_item 없음)
    result.final_permission, result.final_reason = decide_final_permission(
        None, result.signal, None)
    return result

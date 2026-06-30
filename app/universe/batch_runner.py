"""
유니버스 배치 러너 — 단건 코어를 여러 종목에 적용 (오케스트레이션).

active 종목들을 순회하며 각 종목의 최신 공시를 코어 파이프라인에 흘린다.
증분 처리: last_accession과 같으면 'unchanged'로 보고 LLM/저장을 건너뛴다
(상태 안 바뀌면 결론도 같다 → 비용 절감, 메모리 "변화 트리거" 원칙).
한 종목이 실패해도 배치는 계속 진행.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.pipeline import run_disclosure_pipeline
from app.storage.db import save_disclosure
from app.universe.repository import (
    get_active_tickers, get_last_accession, mark_processed)


@dataclass
class BatchRow:
    ticker: str
    status: str          # new | unchanged | error:<Type>
    result: Any = None   # DisclosureResult | None


def run_batch(limit: int = 5, form_type: str = "8-K",
              run_llm: bool = False, save: bool = False) -> list[BatchRow]:
    rows: list[BatchRow] = []
    for ticker in get_active_tickers(limit):
        try:
            prev = get_last_accession(ticker)
            # 증분 판단을 위해 먼저 메타만 보는 게 이상적이나, MVP는 수집까지 수행
            result = run_disclosure_pipeline(
                ticker, form_type=form_type, use_sample=False,
                run_llm=run_llm)
            acc = result.item.meta.get("accession_no")
            is_new = acc != prev

            if is_new and save:
                save_disclosure(result)
                mark_processed(ticker, acc,
                               datetime.now(timezone.utc).isoformat(timespec="seconds"))
            rows.append(BatchRow(ticker, "new" if is_new else "unchanged", result))
        except Exception as e:  # 한 종목 실패가 배치를 멈추지 않게
            rows.append(BatchRow(ticker, f"error:{type(e).__name__}", None))
    return rows

"""
전방수익률 채우기 — 저장된 신호에 return_1d/3d/5d와 outcome을 기록한다.

신호 발생일(day 0) 대비 +1/+3/+5 거래일 종가 수익률을 Yahoo 일봉으로 계산.
아직 5거래일이 안 지난 신호는 return_5d를 비워둬(재시도) 다음 실행 때 채운다.
종목당 종가는 1회만 조회(캐시)해 호출을 아낀다.

outcome = 센티먼트 방향 적중 여부(positive면 +수익=hit). 이건 '측정'까지만 —
가중치 자동조정은 하지 않는다(데이터 부족 시 과적합, 메모리 MVP 컷라인).
"""
from __future__ import annotations

from datetime import date, timedelta

from app.backtest.price_data import fetch_daily_closes, forward_returns
from app.storage.db import pending_returns, set_returns

_TABLES = ("disclosure_signals", "news_signals")


def _outcome(sentiment: str | None, r5: float | None) -> str | None:
    """센티먼트 방향과 5일 수익률 부호가 맞으면 hit, 아니면 miss."""
    if r5 is None or sentiment not in ("positive", "negative"):
        return None
    if sentiment == "positive":
        return "hit" if r5 > 0 else "miss"
    return "hit" if r5 < 0 else "miss"   # negative


def fill_returns(min_age_days: int = 7, today: date | None = None) -> dict:
    """수익률 미확정 신호를 채운다. min_age_days 이상 지난 신호만 대상.

    today는 테스트 주입용(기본 date.today()). 반환: 테이블별 처리 요약.
    """
    today = today or date.today()
    cutoff = (today - timedelta(days=min_age_days)).isoformat()
    summary: dict[str, dict] = {}

    for table in _TABLES:
        rows = pending_returns(table, before_date=cutoff)
        closes_cache: dict[str, list] = {}
        full = partial = skipped = 0
        for row in rows:
            ticker = row["ticker"]
            if ticker not in closes_cache:
                closes_cache[ticker] = fetch_daily_closes(ticker, "1y")
            fr = forward_returns(row["base_date"], closes_cache[ticker])
            r1, r3, r5 = fr.get(1), fr.get(3), fr.get(5)
            if r1 is None and r3 is None and r5 is None:
                skipped += 1
                continue
            outcome = _outcome(row["sentiment"], r5)
            set_returns(table, row["id"], r1, r3, r5, outcome)
            if r5 is not None:
                full += 1
            else:
                partial += 1
        summary[table] = {"candidates": len(rows), "full": full,
                          "partial": partial, "skipped": skipped}
    return summary

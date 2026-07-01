"""
가격 데이터 (백테스트 전방수익률용). Yahoo chart v8 일봉 종가, 키 불필요.

신호 발생일(day 0) 종가 대비 +1/+3/+5 **거래일** 종가의 수익률을 구한다.
아직 그만큼의 거래일이 지나지 않았으면 해당 구간은 비운다(부분 반환).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import httpx

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"


def fetch_daily_closes(ticker: str, range_: str = "1y") -> list[tuple[date, float]]:
    """일봉 종가를 (거래일, 종가) 오름차순 리스트로. 실패 시 빈 리스트."""
    try:
        r = httpx.get(_CHART_URL.format(sym=ticker.upper()),
                      params={"range": range_, "interval": "1d"},
                      headers=_UA, timeout=25)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        ts = res["timestamp"]
        closes = res["indicators"]["quote"][0]["close"]
    except Exception:
        return []
    out: list[tuple[date, float]] = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        d = datetime.fromtimestamp(t, timezone.utc).date()
        out.append((d, float(c)))
    out.sort(key=lambda x: x[0])
    return out


def _parse_date(base: str | date) -> date:
    if isinstance(base, date):
        return base
    return date.fromisoformat(str(base)[:10])   # ISO 앞 10자


def forward_returns(base_date: str | date, closes: list[tuple[date, float]],
                    horizons: tuple[int, ...] = (1, 3, 5)) -> dict[int, float]:
    """base_date(day 0) 종가 대비 +h 거래일 종가 수익률(%)을 horizon별로.

    closes는 fetch_daily_closes 결과(재사용해 종목당 1회 호출). day 0은
    base_date 이하의 마지막 거래일. 미래 거래일이 없으면 그 horizon은 생략.
    """
    if not closes:
        return {}
    bd = _parse_date(base_date)
    # day 0 = base_date 이하 마지막 거래일 인덱스
    i0 = None
    for i, (d, _) in enumerate(closes):
        if d <= bd:
            i0 = i
        else:
            break
    if i0 is None:
        return {}
    base_close = closes[i0][1]
    if base_close == 0:
        return {}
    out: dict[int, float] = {}
    for h in horizons:
        j = i0 + h
        if j < len(closes):
            out[h] = round((closes[j][1] / base_close - 1.0) * 100.0, 3)
    return out

"""
유니버스 시드 — MVP 시작용 대표 대형주 ~50개.

시총 상위 2000개 정렬은 별도 데이터(yfinance/Finnhub)가 필요해 나중에 채운다.
지금은 대표 종목으로 시작하고, CIK·이름은 SEC company_tickers.json에서 자동 매핑.
(market_cap 컬럼은 비워두고 추후 배치로 채움)
"""
from __future__ import annotations

SEED_TICKERS = [
    # 빅테크/반도체
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "TSLA",
    "ORCL", "AMD", "ADBE", "CRM", "NFLX", "INTC", "CSCO", "QCOM",
    "TXN", "AMAT", "MU", "INTU", "NOW", "PANW", "SNPS", "CDNS",
    "LRCX", "KLAC", "ADI", "MRVL",
    # 금융/소비/헬스/산업
    "JPM", "V", "MA", "BAC", "WMT", "XOM", "JNJ", "PG",
    "HD", "KO", "PEP", "COST", "MRK", "ABBV", "LLY", "CVX",
    "UNH", "DIS", "NKE", "MCD", "CAT", "BA",
]


def load_seed() -> tuple[int, int]:
    """시드 티커를 SEC에서 CIK·이름 매핑해 companies에 적재. (loaded, skipped)."""
    from app.collectors.sec_collector import _ticker_map
    from app.universe.repository import upsert_company

    tmap = _ticker_map()
    loaded = skipped = 0
    for t in SEED_TICKERS:
        row = tmap.get(t.upper())
        if not row:
            skipped += 1
            continue
        upsert_company(t, f"{int(row['cik_str']):010d}", row.get("title", t))
        loaded += 1
    return loaded, skipped


def load_sec_universe(limit: int | None = None) -> int:
    """SEC company_tickers.json의 전체(또는 limit) 후보를 companies에 적재.

    2000개 확장의 후보 풀. 시총은 비운 채 넣고, 이후 enrich→reprioritize로
    상위 N만 active 유지한다. 반환: 적재(upsert) 건수.
    """
    from app.collectors.sec_collector import _ticker_map
    from app.universe.repository import upsert_company

    tmap = _ticker_map()
    n = 0
    for t, row in tmap.items():
        if limit is not None and n >= limit:
            break
        upsert_company(t, f"{int(row['cik_str']):010d}", row.get("title", t))
        n += 1
    return n

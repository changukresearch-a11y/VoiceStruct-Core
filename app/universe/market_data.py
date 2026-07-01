"""
Yahoo Finance 시총 수집기 (키 불필요, 배치).

유니버스 우선순위(priority)를 시가총액으로 정하기 위해 market_cap을 채운다.
Yahoo v7 quote는 쿠키+crumb 인증이 필요해졌으므로(2024~), 세션에서 한 번
crumb를 받아 재사용하고, 여러 심볼을 한 번에 조회한다(2000개면 ~수십 콜).

한 종목이 없거나 실패해도 전체를 멈추지 않는다(결과 dict에서 빠질 뿐).
"""
from __future__ import annotations

import time

import httpx

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
_COOKIE_URL = "https://fc.yahoo.com"


class _YahooSession:
    """쿠키+crumb를 1회 확보해 재사용하는 경량 세션."""

    def __init__(self) -> None:
        self._client = httpx.Client(headers=_UA, timeout=25, follow_redirects=True)
        self._crumb: str | None = None

    def _ensure_crumb(self) -> str:
        if self._crumb:
            return self._crumb
        self._client.get(_COOKIE_URL)                       # 쿠키 심기
        r = self._client.get(_CRUMB_URL)
        r.raise_for_status()
        crumb = r.text.strip()
        if not crumb or "<html" in crumb.lower():
            raise RuntimeError("Yahoo crumb 획득 실패")
        self._crumb = crumb
        return crumb

    def quote(self, symbols: list[str]) -> list[dict]:
        crumb = self._ensure_crumb()
        r = self._client.get(
            _QUOTE_URL, params={"symbols": ",".join(symbols), "crumb": crumb})
        r.raise_for_status()
        return r.json().get("quoteResponse", {}).get("result") or []


def fetch_market_caps(symbols: list[str], batch: int = 60,
                      polite_delay: float = 0.3) -> dict[str, dict]:
    """심볼 리스트의 시총 등을 배치로 조회.

    반환: {TICKER: {"market_cap": float|None, "shares": int|None,
                    "sector": None, "name": str|None}}
    (Yahoo v7 quote엔 sector가 없어 None. 필요 시 quoteSummary로 후속 보강.)
    """
    sess = _YahooSession()
    out: dict[str, dict] = {}
    for i in range(0, len(symbols), batch):
        chunk = [s.upper() for s in symbols[i:i + batch]]
        try:
            rows = sess.quote(chunk)
        except Exception:
            continue  # 이 배치 실패 → 다음 배치 계속
        for row in rows:
            sym = (row.get("symbol") or "").upper()
            if not sym:
                continue
            out[sym] = {
                "market_cap": row.get("marketCap"),
                "shares": row.get("sharesOutstanding"),
                "sector": None,
                "name": row.get("longName") or row.get("shortName"),
            }
        time.sleep(polite_delay)  # rate limit 예의
    return out

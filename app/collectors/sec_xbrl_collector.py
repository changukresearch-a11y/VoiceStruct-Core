"""
SEC XBRL 수치 수집기 (10-Q/10-K용).

data.sec.gov/api/xbrl/companyconcept API로 확정 재무수치를 직접 가져와
YoY 변화율을 코드로 계산한다. (무료, 키 불필요 — User-Agent만)

회사마다 us-gaap 태그가 달라서 태그 후보를 순서대로 시도한다.
"""
from __future__ import annotations

import time

import httpx

from app.collectors.sec_collector import _headers, _ticker_to_cik
from app.common.schemas import NormalizedItem
from app.schemas.xbrl_metrics import XbrlMetrics

_CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/us-gaap/{tag}.json"

# (지표명: (태그 후보 순서, 단위))
_CONCEPTS: dict[str, tuple[list[str], str]] = {
    "revenue": (
        ["RevenueFromContractWithCustomerExcludingAssessedTax",
         "Revenues", "SalesRevenueNet"], "USD"),
    "operating_income": (["OperatingIncomeLoss"], "USD"),
    "net_income": (["NetIncomeLoss"], "USD"),
    "eps_diluted": (["EarningsPerShareDiluted"], "USD/shares"),
}


def _get_concept(cik10: str, tag: str) -> list[dict] | None:
    """companyconcept 호출 → units 항목 리스트. 회사가 그 태그를 안 쓰면 None."""
    url = _CONCEPT_URL.format(cik10=cik10, tag=tag)
    r = httpx.get(url, headers=_headers(), timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json().get("units", {})


def _latest_and_yoy(units: dict, unit_key: str) -> tuple[float | None, float | None, dict | None]:
    """정기보고(10-Q/10-K) 항목 중 최신값과 전년 동기 대비 YoY%를 반환."""
    rows = units.get(unit_key, [])
    rep = [x for x in rows if x.get("form") in ("10-Q", "10-K") and x.get("fp") and x.get("end")]
    if not rep:
        return None, None, None
    rep.sort(key=lambda x: x["end"])
    latest = rep[-1]
    prior = [x for x in rep if x.get("fp") == latest["fp"] and x.get("fy") == latest.get("fy", 0) - 1]
    yoy = None
    if prior and prior[-1]["val"]:
        yoy = round((latest["val"] - prior[-1]["val"]) / abs(prior[-1]["val"]) * 100, 1)
    return latest["val"], yoy, latest


def fetch_xbrl_metrics(ticker: str) -> XbrlMetrics:
    """ticker의 최신 정기보고 재무수치 + YoY를 XbrlMetrics로 반환."""
    cik10, _ = _ticker_to_cik(ticker)
    out: dict[str, float | None] = {}
    fiscal: str | None = None
    filed_at: str | None = None

    for metric, (tags, unit) in _CONCEPTS.items():
        units = None
        for tag in tags:
            units = _get_concept(cik10, tag)
            time.sleep(0.12)  # rate limit 예의
            if units:
                break
        if not units:
            out[metric] = None
            out[f"{metric}_yoy_pct"] = None
            continue
        val, yoy, latest = _latest_and_yoy(units, unit)
        out[metric] = val
        out[f"{metric}_yoy_pct"] = yoy
        if fiscal is None and latest:
            fiscal = f"{latest.get('fy')} {latest.get('fp')}"
            filed_at = latest.get("filed")   # companyconcept의 제출일

    return XbrlMetrics(fiscal=fiscal, filed_at=filed_at, **out)


def fetch_latest_financials(ticker: str) -> tuple[NormalizedItem, XbrlMetrics]:
    """10-Q/10-K 경로용. XBRL 수치를 뽑아 LLM 입력 NormalizedItem과 함께 반환.

    본문 전체(수백 페이지) 대신 확정 수치 요약을 body로 쓴다(토큰 절약 + 환각 방지).
    form_type은 최신 보고가 연간(FY)이면 10-K, 분기면 10-Q로 추정.
    """
    _, name = _ticker_to_cik(ticker)
    metrics = fetch_xbrl_metrics(ticker)
    form_type = "10-K" if (metrics.fiscal or "").endswith("FY") else "10-Q"

    item = NormalizedItem(
        source_type="disclosure",
        ticker=ticker.upper(),
        company_name=name,
        title=f"{ticker.upper()} {form_type} — {metrics.fiscal}",
        body=f"정기보고({form_type}) 확정 재무수치 (SEC XBRL):\n{metrics.summary_line()}",
        meta={"form_type": form_type, "fiscal": metrics.fiscal,
              "filed_at": metrics.filed_at, "metrics": metrics.model_dump()},
    )
    return item, metrics

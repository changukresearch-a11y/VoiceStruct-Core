"""
SEC EDGAR 공시 수집기 (Walking Skeleton의 입구).

ticker → 최신 8-K 원문 + Item 번호를 NormalizedItem으로 반환.

SEC 요구사항:
  - User-Agent 헤더 필수 (env SEC_USER_AGENT, 예 "Name email@x.com")
  - rate limit: 10 req/sec 이하 (여기선 호출 사이 짧은 sleep)

흐름:
  1) ticker → CIK            (company_tickers.json, 캐시)
  2) submissions API         (최신 8-K accession/primaryDocument/items)
  3) primaryDocument 다운로드 → HTML 텍스트화
  4) items 필드의 Item 번호로 해당 섹션만 청킹 (토큰 절약)
"""
from __future__ import annotations

import html
import os
import re
import time
from functools import lru_cache

import httpx

from app.common.schemas import NormalizedItem

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}"

_MAX_BODY_CHARS = 6000  # LLM 토큰 절약용 상한

# 배선 검증용 샘플 8-K (use_sample=True)
_SAMPLE_8K = NormalizedItem(
    source_type="disclosure",
    ticker="NVDA",
    company_name="NVIDIA Corporation",
    title="NVDA 8-K — Item 2.02 Results of Operations",
    body=(
        "Item 2.02 Results of Operations and Financial Condition. "
        "NVIDIA today announced record quarterly revenue, up 18% year over year, "
        "with data center revenue reaching an all-time high. The company raised "
        "its guidance for the next quarter."
    ),
    url="https://www.sec.gov/Archives/edgar/data/0001045810/sample-8k.htm",
    meta={"form_type": "8-K", "item_no": "2.02", "cik": "1045810"},
)


def _headers() -> dict[str, str]:
    ua = os.getenv("SEC_USER_AGENT")
    if not ua:
        raise RuntimeError(
            "SEC_USER_AGENT 환경변수가 필요합니다 (SEC 요구). "
            '예: SEC_USER_AGENT="Quantinue you@example.com"'
        )
    return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}


@lru_cache(maxsize=1)
def _ticker_map() -> dict[str, dict]:
    r = httpx.get(SEC_TICKERS_URL, headers=_headers(), timeout=30)
    r.raise_for_status()
    return {row["ticker"].upper(): row for row in r.json().values()}


def _ticker_to_cik(ticker: str) -> tuple[str, str]:
    row = _ticker_map().get(ticker.upper())
    if not row:
        raise ValueError(f"CIK를 찾지 못했습니다: {ticker}")
    cik = int(row["cik_str"])
    return f"{cik:010d}", row.get("title", ticker)


def _latest_8k_meta(cik10: str) -> dict:
    r = httpx.get(SEC_SUBMISSIONS_URL.format(cik10=cik10), headers=_headers(), timeout=30)
    r.raise_for_status()
    recent = r.json()["filings"]["recent"]
    items_col = recent.get("items", [""] * len(recent["form"]))
    for i, form in enumerate(recent["form"]):
        if form == "8-K":
            return {
                "accession": recent["accessionNumber"][i],
                "primary_doc": recent["primaryDocument"][i],
                "filed_at": recent["filingDate"][i],
                "items": items_col[i],
            }
    raise ValueError(f"최근 제출에서 8-K를 찾지 못했습니다: CIK {cik10}")


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _html_to_text(raw_html: str) -> str:
    text = _TAG_RE.sub(" ", raw_html)
    text = html.unescape(text)          # &#8220; &amp; &nbsp; 등 모두 디코딩
    return _WS_RE.sub(" ", text).strip()


def _pick_item(items_field: str) -> str | None:
    """'2.02,9.01' → 첫 실질 Item. 9.01(첨부)만 있으면 9.01."""
    items = [x.strip() for x in items_field.split(",") if x.strip()]
    if not items:
        return None
    non_aux = [x for x in items if x != "9.01"]
    return (non_aux or items)[0]


def _chunk_item_section(text: str, item_no: str) -> str:
    """본문에서 해당 Item 섹션만 도려냄 (다음 Item/서명부 직전까지)."""
    pat = re.compile(
        rf"(Item\s+{re.escape(item_no)}.*?)(?=Item\s+\d\.\d\d|SIGNATURE|$)",
        re.IGNORECASE | re.DOTALL,
    )
    m = pat.search(text)
    return m.group(1).strip() if m else text


def fetch_latest_8k(ticker: str, use_sample: bool = True) -> NormalizedItem:
    """ticker의 최신 8-K를 NormalizedItem으로 반환.

    use_sample=True : 내장 샘플 (네트워크/키 불필요, 배선 검증).
    use_sample=False: 실제 SEC EDGAR 호출 (SEC_USER_AGENT 필요).
    """
    if use_sample:
        return _SAMPLE_8K

    cik10, name = _ticker_to_cik(ticker)
    cik = str(int(cik10))
    meta = _latest_8k_meta(cik10)

    acc_nodash = meta["accession"].replace("-", "")
    doc_url = SEC_ARCHIVES_URL.format(
        cik=cik, acc_nodash=acc_nodash, doc=meta["primary_doc"])
    time.sleep(0.2)  # rate limit 예의
    r = httpx.get(doc_url, headers=_headers(), timeout=30)
    r.raise_for_status()

    text = _html_to_text(r.text)
    item_no = _pick_item(meta["items"])           # SEC 메타 우선
    body = _chunk_item_section(text, item_no) if item_no else text
    body = body[:_MAX_BODY_CHARS]

    return NormalizedItem(
        source_type="disclosure",
        ticker=ticker.upper(),
        company_name=name,
        title=(f"{ticker.upper()} 8-K — Item {item_no}" if item_no
               else f"{ticker.upper()} 8-K"),
        body=body,
        url=doc_url,
        meta={
            "form_type": "8-K",
            "item_no": item_no,
            "cik": cik,
            "accession_no": meta["accession"],
            "filed_at": meta["filed_at"],
            "items_raw": meta["items"],
        },
    )

"""
Form 4 (내부자 거래) 수집기 — raw XML 파싱 (LLM 미사용).

submissions에서 최신 Form 4를 찾아 raw XML(primaryDocument의 XSL 경로 prefix 제거)을
내려받아 거래 내역을 구조화한다.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import httpx

from app.collectors.sec_collector import (
    SEC_ARCHIVES_URL, SEC_SUBMISSIONS_URL, _headers, _ticker_to_cik)
from app.common.schemas import NormalizedItem
from app.schemas.form4 import Form4Filing, Form4Transaction


def _latest_form4_meta(cik10: str) -> dict:
    r = httpx.get(SEC_SUBMISSIONS_URL.format(cik10=cik10), headers=_headers(), timeout=30)
    r.raise_for_status()
    recent = r.json()["filings"]["recent"]
    for i, form in enumerate(recent["form"]):
        if form == "4":
            return {
                "accession": recent["accessionNumber"][i],
                "primary_doc": recent["primaryDocument"][i],
                "filed_at": recent["filingDate"][i],
            }
    raise ValueError(f"최근 제출에서 Form 4를 찾지 못했습니다: CIK {cik10}")


def _txt(node, path) -> str | None:
    return node.findtext(path) if node is not None else None


def _parse_transactions(root, table: str, is_deriv: bool) -> list[Form4Transaction]:
    out: list[Form4Transaction] = []
    for tx in root.findall(f".//{table}"):
        code = _txt(tx, ".//transactionCode")
        shares = _txt(tx, ".//transactionShares/value")
        if code is None or shares is None:
            continue
        out.append(Form4Transaction(
            code=code,
            shares=float(shares),
            price=(lambda p: float(p) if p else None)(
                _txt(tx, ".//transactionPricePerShare/value")),
            acquired_disposed=_txt(tx, ".//transactionAcquiredDisposedCode/value") or "",
            is_derivative=is_deriv,
        ))
    return out


def fetch_latest_form4(ticker: str) -> tuple[NormalizedItem, Form4Filing]:
    cik10, name = _ticker_to_cik(ticker)
    cik = str(int(cik10))
    meta = _latest_form4_meta(cik10)

    raw_doc = re.sub(r"^.*/", "", meta["primary_doc"])  # xslF345X06/form4.xml → form4.xml
    url = SEC_ARCHIVES_URL.format(
        cik=cik, acc_nodash=meta["accession"].replace("-", ""), doc=raw_doc)
    xml_text = httpx.get(url, headers=_headers(), timeout=30).text
    root = ET.fromstring(xml_text)

    rel = root.find(".//reportingOwnerRelationship")
    filing = Form4Filing(
        ticker=(_txt(root, ".//issuerTradingSymbol") or ticker).upper(),
        company_name=name,
        owner_title=_txt(rel, "officerTitle"),
        is_officer=(_txt(rel, "isOfficer") or "").lower() in ("1", "true"),
        is_director=(_txt(rel, "isDirector") or "").lower() in ("1", "true"),
        is_10b5_1="10b5-1" in xml_text.lower(),
        transactions=(_parse_transactions(root, "nonDerivativeTransaction", False)
                      + _parse_transactions(root, "derivativeTransaction", True)),
        accession_no=meta["accession"],
        url=url,
    )

    tx_summary = "; ".join(
        f"{t.code} {t.shares:.0f}주" + (f"@${t.price:.2f}" if t.price else "")
        for t in filing.transactions) or "(거래 없음)"
    item = NormalizedItem(
        source_type="disclosure",
        ticker=filing.ticker,
        company_name=name,
        title=f"{filing.ticker} Form 4 — {filing.owner_title or '내부자'}",
        body=f"내부자거래(Form 4) · {filing.owner_title or '내부자'} · {tx_summary}",
        url=url,
        meta={"form_type": "4", "filed_at": meta["filed_at"],
              "accession_no": meta["accession"], "owner_title": filing.owner_title},
    )
    return item, filing

"""
뉴스 수집기 (공시 sec_collector와 별도, 공통 NormalizedItem 반환).

실수집: Google News RSS (키 불필요). <source> 태그가 출처명+도메인을 제공해
출처 4단계 정책(source_trust_policy)에 바로 연결된다. 신호는 헤드라인에 집중.
fetch_sample_news()는 배선 검증용 내장 샘플로 유지.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

from app.common.schemas import NormalizedItem

_GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")
_UA = {"User-Agent": "Mozilla/5.0 (Quantinue research)"}

# 배선 검증용 샘플 (출처/키워드 필터를 태우기 좋게 몇 종류)
_SAMPLES: dict[str, NormalizedItem] = {
    "good": NormalizedItem(
        source_type="news",
        ticker="NVDA",
        company_name="NVIDIA Corporation",
        title="NVIDIA announces $50 billion share buyback program",
        body="NVIDIA announced a new share buyback (repurchase) program worth "
             "$50 billion, signaling confidence in future cash flow.",
        url="https://www.reuters.com/markets/nvidia-buyback",
        meta={"source": "reuters.com"},
    ),
    "rumor": NormalizedItem(
        source_type="news",
        ticker="ABCD",
        company_name="Example Corp",
        title="ABCD reportedly in talks for acquisition, sources say",
        body="ABCD is reportedly in early talks for a potential acquisition, "
             "according to people familiar with the matter.",
        url="https://stocktwits.com/abcd-rumor",
        meta={"source": "stocktwits.com"},
    ),
    "noise": NormalizedItem(
        source_type="news",
        ticker="XYZ",
        company_name="XYZ Inc.",
        title="Why XYZ shares are trading higher today",
        body="Here are the top stocks to watch and why XYZ shares are moving.",
        url="https://www.fool.com/xyz-why",
        meta={"source": "fool.com"},
    ),
}


def fetch_sample_news(kind: str = "good") -> NormalizedItem:
    """배선 검증용 샘플 뉴스 반환. kind: good | rumor | noise."""
    return _SAMPLES[kind]


def fetch_latest_news(ticker: str, limit: int = 8) -> list[NormalizedItem]:
    """Google News RSS에서 ticker 관련 최신 뉴스를 NormalizedItem 리스트로."""
    url = _GOOGLE_NEWS_RSS.format(q=f"{ticker}+stock")
    r = httpx.get(url, headers=_UA, timeout=30, follow_redirects=True)
    r.raise_for_status()
    root = ET.fromstring(r.text)

    items: list[NormalizedItem] = []
    for it in root.findall(".//item")[:limit]:
        title = (it.findtext("title") or "").strip()
        src = it.find("source")
        src_name = src.text if src is not None else None
        src_url = src.get("url") if src is not None else None

        published = None
        pub = it.findtext("pubDate")
        if pub:
            try:
                published = parsedate_to_datetime(pub)
            except (TypeError, ValueError):
                published = None

        items.append(NormalizedItem(
            source_type="news",
            ticker=ticker.upper(),
            title=title,
            body=title,  # RSS 본문은 빈약 → 헤드라인 중심 분석
            url=src_url or it.findtext("link"),
            published_at=published,
            meta={"source": src_name or "", "google_link": it.findtext("link")},
        ))
    return items

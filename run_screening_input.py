"""
스크리닝(스케일러) → 정보분석 입력 로더.

스크리닝 에이전트가 준 종목 리스트(JSON)를 읽어:
  1) 유니버스(companies 테이블)에 적재 — priority=rank 로 스크리닝 순위를
     우리 처리 순서에 반영. cik/회사명이 없으면 SEC에서 자동 매핑.
  2) (--run) 각 종목의 공시·뉴스를 돌려 Strategist 입력 번들
     (DisclosureBundle / NewsBundle 2객체)을 생성. category 는 파일→메모리
     →번들로 **그대로 통과**하므로 companies 스키마 변경이 필요 없다.

입력 형식은 `스크리닝_입력스키마_스크리닝→정보분석.md` 참고.
기존 서비스 코드(수집·분석·저장·번들)는 손대지 않고 그대로 재사용한다.

    # 적재만 (유니버스에 넣고 스케줄러/유니버스 러너로 돌릴 준비)
    python run_screening_input.py --file screening_input.json

    # 적재 + 종목별 번들 생성(공시+뉴스) — category 통과
    python run_screening_input.py --file screening_input.json --run --llm --json --limit 5

    # 적재 건너뛰고 번들만 (이미 적재돼 있을 때)
    python run_screening_input.py --file screening_input.json --run --no-load
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(override=True)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ── 파싱 ────────────────────────────────────────────────

def _load_json(path: Path) -> list[dict]:
    """봉투({companies:[...]}) 또는 순수 배열([...]) 둘 다 허용."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        companies = data.get("companies")
        if companies is None:
            raise ValueError("봉투에 'companies' 배열이 없습니다.")
        declared = data.get("count")
        if declared is not None and declared != len(companies):
            print(f"⚠️  count={declared} 인데 실제 {len(companies)}개 "
                  f"(불일치 — 배열 기준으로 진행)")
        return companies
    if isinstance(data, list):
        return data
    raise ValueError("최상위는 배열 또는 {companies:[...]} 봉투여야 합니다.")


def _norm_cik(raw: Any) -> str | None:
    """cik 를 10자리 zero-pad 문자열로. 숫자 아니면 그대로."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    return f"{int(s):010d}" if s.isdigit() else s


def _norm(entry: dict) -> dict | None:
    """원소 1개 정규화. ticker 없으면 None(스킵)."""
    ticker = str(entry.get("ticker") or "").strip().upper()
    if not ticker:
        return None
    rank = entry.get("rank")
    return {
        "ticker": ticker,
        "category": (entry.get("category") or None),
        "rank": int(rank) if isinstance(rank, (int, float, str)) and str(rank).strip()
                and str(rank).strip().lstrip("-").isdigit() else None,
        "company_name": (entry.get("company_name") or None),
        "cik": _norm_cik(entry.get("cik")),
        "sector": (entry.get("sector") or None),
    }


# ── 적재 ────────────────────────────────────────────────

def load_universe(companies: list[dict], exclusive: bool = False) -> dict:
    """스크리닝 종목을 companies 테이블에 upsert. rank→priority.

    cik/회사명이 없는 종목이 하나라도 있을 때만 SEC company_tickers.json 을
    1회 내려받아 자동 매핑한다(전부 제공되면 네트워크 호출 없음).

    ※ 기존 `upsert_company` 는 ON CONFLICT 시 priority 를 갱신하지 않는다
      (다른 호출부가 기본값 100 으로 시총순위를 덮어쓰지 않도록 한 의도).
      그래서 스크리닝 rank 는 upsert 후 여기서 **명시적으로** 반영한다.
    exclusive=True 면 스크리닝 목록만 active=1, 나머지 전부 비활성화 →
      스케줄러 working-set 이 곧 스크리닝 50개가 된다.
    """
    from app.universe.repository import _conn, count, upsert_company

    need_map = any(not c["cik"] or not c["company_name"] for c in companies)
    tmap: dict = {}
    if need_map:
        from app.collectors.sec_collector import _ticker_map
        tmap = _ticker_map()

    loaded = unmapped = 0
    for c in companies:
        cik, name = c["cik"], c["company_name"]
        if (not cik or not name) and tmap:
            row = tmap.get(c["ticker"])
            if row:
                cik = cik or f"{int(row['cik_str']):010d}"
                name = name or row.get("title")
        if not cik:
            unmapped += 1
            print(f"  ⚠️  {c['ticker']:6} CIK 매핑 실패 — 그래도 적재(수집 시 실패 가능)")
        upsert_company(c["ticker"], cik, name)
        loaded += 1

    # priority(=rank) · active 를 스크리닝 기준으로 확정 (신규/기존 종목 모두)
    marks = {c["ticker"] for c in companies}
    deactivated = 0
    with _conn() as conn:
        for c in companies:
            priority = c["rank"] if c["rank"] is not None else 100
            conn.execute(
                "UPDATE companies SET priority=?, active=1 WHERE ticker=?",
                (priority, c["ticker"]))
        if exclusive:
            for (t,) in conn.execute("SELECT ticker FROM companies").fetchall():
                if t not in marks:
                    conn.execute(
                        "UPDATE companies SET active=0 WHERE ticker=?", (t,))
                    deactivated += 1
    return {"loaded": loaded, "unmapped": unmapped,
            "deactivated": deactivated, "total": count()}


# ── 번들 생성 (기존 파이프라인 재사용) ──────────────────────

def build_bundles(ticker: str, category: str | None, company_name: str | None,
                  form: str, news_limit: int, run_llm: bool) -> tuple:
    """한 종목의 공시·뉴스를 돌려 (DisclosureBundle, NewsBundle) 반환.

    run_bundle.py 와 동일한 로직 — category 를 그대로 통과시킨다.
    """
    from app.collectors.news_collector import fetch_latest_news
    from app.common.analysis_bundle import (build_disclosure_bundle,
                                            build_news_bundle)
    from app.news_pipeline import run_news_pipeline
    from app.pipeline import run_disclosure_pipeline

    disc = run_disclosure_pipeline(
        ticker, form_type=form, use_sample=False, run_llm=run_llm)
    items = fetch_latest_news(ticker, limit=news_limit)
    news_results = [run_news_pipeline(it, run_llm=run_llm) for it in items]

    trade_date = date.today().isoformat()
    # 회사명(company_name)·카테고리(category)는 번들에서 제거됨 — tb_universe에
    # 이미 있어 Strategist가 JOIN으로 읽는다(팀 명세 2026-07-06). 유니버스 적재는
    # 별도 경로(로더)가 이미 처리하므로 여기선 번들에 넣지 않는다.
    d_bundle = build_disclosure_bundle(
        ticker, trade_date, disclosure_result=disc)
    n_bundle = build_news_bundle(
        ticker, trade_date, news_results=news_results)
    passed = sum(1 for r in news_results if not r.dropped)
    return d_bundle, n_bundle, len(items), passed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="screening_input.json",
                    help="스크리닝 입력 JSON 경로")
    ap.add_argument("--no-load", action="store_true",
                    help="유니버스 적재 건너뛰기(이미 적재된 경우)")
    ap.add_argument("--exclusive", action="store_true",
                    help="스크리닝 목록만 active, 나머지 전부 비활성(working-set=이 50개)")
    ap.add_argument("--run", action="store_true",
                    help="적재 후 종목별 번들(공시+뉴스) 생성")
    ap.add_argument("--form", default="8-K", choices=["8-K", "10-Q", "10-K", "4"])
    ap.add_argument("--news-limit", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None,
                    help="--run 시 상위 N개만(스크리닝 순위 순)")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--json", action="store_true", help="번들 JSON도 출력")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"❌ 파일 없음: {path}")
        sys.exit(1)

    raw = _load_json(path)
    companies = [c for c in (_norm(e) for e in raw) if c]
    dropped = len(raw) - len(companies)
    print(f"📥 스크리닝 입력 {len(raw)}건 → 유효 {len(companies)}건"
          + (f" (ticker 없음 {dropped}건 스킵)" if dropped else ""))

    # rank 순 정렬(없는 건 뒤로) — 처리·출력 순서를 스크리닝 순위에 맞춤
    companies.sort(key=lambda c: (c["rank"] is None, c["rank"] or 0, c["ticker"]))

    if not args.no_load:
        r = load_universe(companies, exclusive=args.exclusive)
        note = f" · 비활성화 {r['deactivated']}" if args.exclusive else ""
        print(f"🌐 유니버스 적재: {r['loaded']}개 upsert "
              f"(CIK 미매핑 {r['unmapped']}{note}) · 현재 총 {r['total']}개\n")

    if not args.run:
        if args.no_load:
            print("ℹ️  --no-load 이고 --run 도 아니라 할 일이 없습니다.")
        return

    run_llm = args.llm and bool(
        os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
    if args.llm and not run_llm:
        print("⚠️  LLM 키 없음 → 분석 없이 빈 번들 (.env 확인)\n")

    targets = companies[:args.limit] if args.limit else companies
    print(f"▶️  번들 생성 {len(targets)}종목 (form={args.form}, "
          f"news≤{args.news_limit}, llm={run_llm})\n")

    for i, c in enumerate(targets, start=1):
        tk, cat = c["ticker"], c["category"]
        print("=" * 60)
        print(f"[{i}/{len(targets)}] {tk}"
              + (f" · {cat}" if cat else "") + f"  (rank={c['rank']})")
        try:
            d_b, n_b, n_items, n_pass = build_bundles(
                tk, cat, c["company_name"], args.form, args.news_limit, run_llm)
        except Exception as e:
            print(f"  ⚠️  실패: {type(e).__name__}: {e}")
            continue
        print(f"  뉴스 {n_items}건 수집 · 사전필터 통과 {n_pass}")
        print("\n📄 " + d_b.to_prompt())
        print("\n📰 " + n_b.to_prompt())
        if args.json:
            print("\n📋 DisclosureBundle JSON:")
            print(d_b.model_dump_json())
            print("📋 NewsBundle JSON:")
            print(n_b.model_dump_json())
    print("=" * 60)


if __name__ == "__main__":
    main()

"""
Bundle 생성기 — 한 종목의 공시·뉴스를 돌려 Strategist 입력 번들 2개를 만든다.

    python run_bundle.py --ticker NVDA --form 8-K --news-limit 8 --llm --save

공시·뉴스는 **완전 별개 2객체**(DisclosureBundle / NewsBundle)로 분리 산출한다.
모든 점수는 0~1 소수점, 방향은 sentiment 라벨.
--save 면 tb_disclosure/tb_news 스냅샷으로 저장(Strategist가 최신 행 읽음).
(팀 명세 2026-07-06 반영: 회사명·카테고리는 tb_universe JOIN, 번들에서 제거)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

from dotenv import load_dotenv

load_dotenv(override=True)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.collectors.news_collector import fetch_latest_news
from app.common.analysis_bundle import (build_disclosure_bundle,
                                        build_news_bundle)
from app.news_pipeline import run_news_pipeline
from app.pipeline import run_disclosure_pipeline


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="NVDA")
    ap.add_argument("--form", default="8-K", choices=["8-K", "10-Q", "10-K", "4"])
    ap.add_argument("--news-limit", type=int, default=8)
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--json", action="store_true", help="번들 JSON도 출력")
    ap.add_argument("--save", action="store_true",
                    help="tb_disclosure/tb_news 스냅샷으로 저장")
    args = ap.parse_args()

    run_llm = args.llm and bool(
        os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
    if args.llm and not run_llm:
        print("⚠️  LLM 키 없음 → 분석 없이 빈 번들이 나옵니다 (.env 확인)")

    # 1) 공시
    print(f"▶️  {args.ticker} 공시({args.form}) 수집·분석 …")
    disc = run_disclosure_pipeline(
        args.ticker, form_type=args.form, use_sample=False, run_llm=run_llm)

    # 2) 뉴스
    print(f"▶️  {args.ticker} 뉴스 수집·분석 (limit {args.news_limit}) …")
    items = fetch_latest_news(args.ticker, limit=args.news_limit)
    news_results = [run_news_pipeline(it, run_llm=run_llm) for it in items]
    passed = sum(1 for r in news_results if not r.dropped)
    print(f"   뉴스 {len(items)}건 수집 · 사전필터 통과 {passed}\n")

    # 3) 번들 — 공시·뉴스 완전 별개 2객체
    trade_date = date.today().isoformat()
    d_bundle = build_disclosure_bundle(
        args.ticker, trade_date, disclosure_result=disc)
    n_bundle = build_news_bundle(
        args.ticker, trade_date, news_results=news_results)

    if args.save:
        from app.storage.db import save_disclosure_bundle, save_news_bundle
        save_disclosure_bundle(d_bundle)
        save_news_bundle(n_bundle)
        print("💾 tb_disclosure/tb_news 스냅샷 저장\n")

    print("=" * 60)
    print("📄 DisclosureBundle.to_prompt() — Strategist 입력(공시):\n")
    print(d_bundle.to_prompt())
    print("\n" + "-" * 60)
    print("📰 NewsBundle.to_prompt() — Strategist 입력(뉴스):\n")
    print(n_bundle.to_prompt())
    print("=" * 60)

    if args.json:
        print("\n📋 DisclosureBundle JSON:")
        print(d_bundle.model_dump_json(indent=2))
        print("\n📋 NewsBundle JSON:")
        print(n_bundle.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

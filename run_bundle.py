"""
AnalysisBundle 생성기 — 한 종목의 공시+뉴스를 돌려 Strategist 입력 번들을 만든다.

    python run_bundle.py --ticker NVDA --form 8-K --news-limit 8 --llm

실제 SEC 공시 + Google News + LLM 분석을 종목당 1개 번들로 집계 → to_prompt() 출력.
(명세: 인터페이스명세_정보분석→Strategist.md)
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
from app.common.analysis_bundle import build_bundle
from app.news_pipeline import run_news_pipeline
from app.pipeline import run_disclosure_pipeline


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="NVDA")
    ap.add_argument("--form", default="8-K", choices=["8-K", "10-Q", "10-K", "4"])
    ap.add_argument("--news-limit", type=int, default=8)
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--json", action="store_true", help="번들 JSON도 출력")
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

    # 3) 번들
    bundle = build_bundle(
        args.ticker, as_of=date.today().isoformat(),
        disclosure_result=disc, news_results=news_results)

    print("=" * 60)
    print("📦 AnalysisBundle.to_prompt() — Strategist가 보는 입력:\n")
    print(bundle.to_prompt())
    print("=" * 60)

    if args.json:
        print("\n📋 JSON (코드/PM용):")
        print(bundle.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

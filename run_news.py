"""
뉴스 파이프라인 엔트리포인트.

    python run_news.py --ticker AAPL                 # 수집 + 사전필터만 (LLM 없이)
    python run_news.py --ticker AAPL --llm           # 통과분 LLM 분석까지
    python run_news.py --ticker AAPL --limit 8 --llm

Google News RSS 실수집 → 출처 3단계 + 키워드 필터 → (통과분) LLM 분석.
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.collectors.news_collector import fetch_latest_news
from app.news_pipeline import run_news_pipeline


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="AAPL")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--llm", action="store_true", help="통과한 뉴스만 LLM 분석")
    ap.add_argument("--save", action="store_true", help="news_signals에 저장(중복 skip)")
    args = ap.parse_args()

    has_key = bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
    run_llm = args.llm and has_key
    if args.llm and not run_llm:
        print("⚠️  LLM 키 없음 → LLM 단계 건너뜀\n")

    items = fetch_latest_news(args.ticker, limit=args.limit)
    print(f"📰 {args.ticker} — 수집 {len(items)}건\n")

    if args.save:
        from app.storage.db import save_news

    passed = dropped = saved = 0
    for i, it in enumerate(items, 1):
        r = run_news_pipeline(it, run_llm=run_llm)
        if args.save and save_news(r) is not None:
            saved += 1
        tag = "🟢" if not r.dropped else "⛔"
        print(f"{tag} [{i}] ({r.source_grade}) {it.meta.get('source')} — {it.title[:70]}")
        kv = r.keyword_verdict
        print(f"      필터: {kv.result}"
              + (f"({kv.category}/{kv.keyword})" if kv.keyword else ""))
        if r.dropped:
            dropped += 1
            print(f"      → drop: {r.final_reason}")
            continue
        passed += 1
        if r.signal:
            s = r.signal
            print(f"      🤖 {s.event_type}/{s.sentiment} imp={s.importance} "
                  f"confirmed={s.is_confirmed} trust={s.source_trust} → {r.final_permission}")
            print(f"         {s.reason}")

    tail = f" · 저장 {saved}" if args.save else ""
    print(f"\n요약: 통과 {passed} · drop {dropped}{tail} · 총 {len(items)}")


if __name__ == "__main__":
    main()

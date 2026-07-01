"""
유니버스 오케스트레이션 엔트리포인트.

    python run_universe.py --seed                       # 시드 50개 적재
    python run_universe.py --run --limit 5              # 배치 처리 (배선)
    python run_universe.py --run --limit 5 --llm --save # + LLM + 저장(증분)
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true", help="대표 시드 50개 적재")
    ap.add_argument("--expand", type=int, metavar="N",
                    help="SEC 후보 N개 적재(2000 확장 풀). 미지정 값 0=전체")
    ap.add_argument("--enrich", action="store_true",
                    help="Yahoo로 시총 채우기(미보유분)")
    ap.add_argument("--enrich-limit", type=int, default=None,
                    help="enrich 대상 최대 개수")
    ap.add_argument("--enrich-all", action="store_true",
                    help="이미 채운 것도 다시 갱신")
    ap.add_argument("--reprioritize", action="store_true",
                    help="priority=시총순위 재산정")
    ap.add_argument("--keep-top", type=int, default=None,
                    help="상위 N만 active=1 (나머지 비활성)")
    ap.add_argument("--run", action="store_true", help="배치 처리 실행")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--form", default="8-K", choices=["8-K", "10-Q", "10-K", "4"])
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    if args.seed:
        from app.universe.seed import load_seed
        from app.universe.repository import count
        loaded, skipped = load_seed()
        print(f"🌐 시드 적재: {loaded}개 (skip {skipped}) · 현재 총 {count()}개")

    if args.expand is not None:
        from app.universe.seed import load_sec_universe
        from app.universe.repository import count
        limit = None if args.expand == 0 else args.expand
        n = load_sec_universe(limit=limit)
        print(f"🌐 SEC 후보 적재: {n}개 upsert · 현재 총 {count()}개")

    if args.enrich:
        from app.universe.market_data import fetch_market_caps
        from app.universe.repository import get_all_tickers, set_market_cap
        targets = get_all_tickers(
            only_missing_cap=not args.enrich_all, limit=args.enrich_limit)
        print(f"💰 시총 조회 대상 {len(targets)}개 …")
        caps = fetch_market_caps(targets)
        filled = 0
        for t in targets:
            info = caps.get(t.upper())
            if info and info.get("market_cap") is not None:
                set_market_cap(t, info["market_cap"], info.get("sector"))
                filled += 1
        print(f"   → 채움 {filled}개 (미조회 {len(targets)-filled})")

    if args.reprioritize:
        from app.universe.repository import reprioritize_by_market_cap
        r = reprioritize_by_market_cap(keep_top=args.keep_top)
        print(f"📊 우선순위 재산정: ranked {r['ranked']} · "
              f"active {r['active']} · 비활성 {r['deactivated']}")

    if args.run:
        from app.universe.batch_runner import run_batch
        run_llm = args.llm and bool(
            os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
        if args.llm and not run_llm:
            print("⚠️  LLM 키 없음 → LLM 건너뜀")
        print(f"▶️  배치 실행: limit={args.limit} form={args.form} "
              f"llm={run_llm} save={args.save}\n")

        rows = run_batch(limit=args.limit, form_type=args.form,
                         run_llm=run_llm, save=args.save)
        new = unchanged = errors = 0
        for r in rows:
            if r.result is None:
                errors += 1
                print(f"  ⚠️  {r.ticker:6} {r.status}")
                continue
            if r.status == "new":
                new += 1
            else:
                unchanged += 1
            sig = r.result.signal
            extra = (f" {sig.event_type}/{sig.sentiment} imp={sig.importance}"
                     if sig else "")
            print(f"  {'🆕' if r.status=='new' else '⏸️ '} {r.ticker:6} "
                  f"[{r.status}] {r.result.item.title[:42]} "
                  f"→ {r.result.final_permission}{extra}")
        print(f"\n요약: new {new} · unchanged {unchanged} · error {errors} "
              f"· 총 {len(rows)}")


if __name__ == "__main__":
    main()

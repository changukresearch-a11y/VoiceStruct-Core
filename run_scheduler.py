"""
수집 스케줄러 엔트리포인트 — 유니버스를 주기적으로(또는 1회) 순회.

    # 1회 순회 (증분 skip 확인, LLM/저장 없이 배선)
    python run_scheduler.py --once --limit 5 --forms 8-K,4

    # 1회 + LLM + 저장 (새 공시만 분석·기록)
    python run_scheduler.py --once --limit 5 --forms 8-K --llm --save

    # 뉴스까지 통합해 주기 실행 (15분 간격, Ctrl+C로 종료)
    python run_scheduler.py --interval 900 --limit 10 --forms 8-K,10-Q --news --llm --save

메타레벨 증분: submissions만 보고 이미 처리한 accession이면 문서 다운로드/LLM을 skip.
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.scheduler.scheduler import run_cycle, run_forever


def _render_cycle(report) -> None:
    """1회 사이클 상세 출력."""
    for f in report.filings:
        if f.status == "unchanged":
            print(f"  ⏸️  {f.ticker:6} {f.form:5} [unchanged] acc={f.accession} (skip)")
        elif f.status == "no-filing":
            print(f"  ·  {f.ticker:6} {f.form:5} [no-filing]")
        elif f.status.startswith("error"):
            print(f"  ⚠️  {f.ticker:6} {f.form:5} {f.status}")
        else:  # new
            r = f.result
            sig = getattr(r, "signal", None)
            extra = (f" {sig.event_type}/{sig.sentiment} imp={sig.importance}"
                     if sig else "")
            title = (r.item.title[:42] if r else "")
            print(f"  🆕 {f.ticker:6} {f.form:5} [new] {title} "
                  f"→ {getattr(r, 'final_permission', '?')}{extra}")
    for nx in report.news:
        if nx.error:
            print(f"  📰 {nx.ticker:6} 뉴스 오류: {nx.error}")
        else:
            print(f"  📰 {nx.ticker:6} 뉴스 fresh {nx.fresh}/{nx.total} "
                  f"→ 통과 {nx.passed}·drop {nx.dropped}·저장 {nx.saved}")
    print(f"\n요약: 공시 new {report.new} · unchanged {report.unchanged} "
          f"· error {report.errors} · 총 {len(report.filings)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="1회만 순회하고 종료")
    ap.add_argument("--interval", type=int, default=900,
                    help="주기 실행 간격(초). --once면 무시")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--forms", default="8-K",
                    help="쉼표 구분 (예: 8-K,10-Q,4)")
    ap.add_argument("--news", action="store_true", help="뉴스도 통합 처리")
    ap.add_argument("--news-limit", type=int, default=6)
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    forms = tuple(x.strip() for x in args.forms.split(",") if x.strip())
    run_llm = args.llm and bool(
        os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
    if args.llm and not run_llm:
        print("⚠️  LLM 키 없음 → LLM 건너뜀")

    kwargs = dict(limit=args.limit, forms=forms, run_news=args.news,
                  news_limit=args.news_limit, run_llm=run_llm, save=args.save)

    if args.once:
        print(f"▶️  1회 순회: limit={args.limit} forms={forms} "
              f"news={args.news} llm={run_llm} save={args.save}\n")
        report = run_cycle(**kwargs)
        _render_cycle(report)
    else:
        print(f"▶️  주기 실행: 매 {args.interval}s · limit={args.limit} "
              f"forms={forms} news={args.news} llm={run_llm} save={args.save}\n"
              f"   (Ctrl+C로 종료)\n")
        run_forever(interval_sec=args.interval, **kwargs)


if __name__ == "__main__":
    main()

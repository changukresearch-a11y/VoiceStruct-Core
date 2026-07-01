"""
백테스트 피드백 엔트리포인트 — 신호에 전방수익률을 채우고 성과를 집계한다.

    python run_backtest.py --fill                 # 5거래일 이상 지난 신호 수익률 채움
    python run_backtest.py --fill --min-age 5
    python run_backtest.py --report               # 이벤트/출처/센티먼트별 성과
    python run_backtest.py --fill --report

수익률/적중률은 '측정'까지만 — 가중치 자동조정은 하지 않는다(과적합 방지, 수동 분석).
"""
from __future__ import annotations

import argparse
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fill", action="store_true", help="전방수익률 채우기")
    ap.add_argument("--min-age", type=int, default=7,
                    help="이 일수 이상 지난 신호만 채움(기본 7)")
    ap.add_argument("--report", action="store_true", help="성과 리포트 출력")
    args = ap.parse_args()

    if not (args.fill or args.report):
        ap.error("--fill 또는 --report 중 하나는 필요")

    if args.fill:
        from app.backtest.fill_returns import fill_returns
        summ = fill_returns(min_age_days=args.min_age)
        print(f"🧮 수익률 채우기 (min_age={args.min_age}일)")
        for table, s in summ.items():
            print(f"  {table:20} 대상 {s['candidates']:>4} · "
                  f"완전 {s['full']} · 부분 {s['partial']} · 보류 {s['skipped']}")
        print()

    if args.report:
        from app.backtest.report import performance_report
        print(performance_report())


if __name__ == "__main__":
    main()

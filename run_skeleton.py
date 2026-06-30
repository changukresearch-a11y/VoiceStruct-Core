"""
Walking Skeleton 엔트리포인트.

    python run_skeleton.py            # 샘플 8-K로 배선만 검증 (LLM 키 불필요)
    python run_skeleton.py --llm      # ANTHROPIC_API_KEY 있으면 LLM 분석까지

흐름이 끝까지 도는지 확인하는 용도.
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

# Windows 콘솔(cp949)에서도 이모지/한글 출력되도록
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.pipeline import run_disclosure_pipeline

load_dotenv(override=True)  # .env 값이 셸 환경변수보다 우선


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="NVDA")
    parser.add_argument("--form", default="8-K", choices=["8-K", "10-Q", "10-K", "4"],
                        help="공시 Form 종류 (10-Q/K=XBRL, 4=내부자거래 코드 스코어링)")
    parser.add_argument("--live", action="store_true",
                        help="실제 SEC EDGAR 수집 (SEC_USER_AGENT 필요)")
    parser.add_argument("--llm", action="store_true",
                        help="LLM 분석까지 실행 (LLM provider 키 필요)")
    parser.add_argument("--save", action="store_true",
                        help="결과를 SQLite(data/quantinue.sqlite)에 저장")
    args = parser.parse_args()

    run_llm = args.llm and bool(os.getenv("ANTHROPIC_API_KEY"))
    if args.llm and not run_llm:
        print("⚠️  ANTHROPIC_API_KEY 없음 → LLM 단계 건너뜀\n")

    result = run_disclosure_pipeline(
        args.ticker, form_type=args.form, use_sample=not args.live, run_llm=run_llm)

    print(f"📄 {result.item.ticker} — {result.item.title}")
    print(f"   form={result.item.meta.get('form_type')} "
          f"item={result.item.meta.get('item_no')}")
    print(f"🧭 Form 경로: {result.route}")
    if result.routed_item:
        print(f"🧭 Item 라우팅: {result.routed_item}")
    if result.metrics:
        print(f"📊 XBRL: {result.metrics.summary_line()}")
    print(f"🛡️  하드리스크: {result.hard_risk}")
    print(f"🤖 LLM 신호: {result.signal}")
    print(f"⚖️  최종 권한: {result.final_permission}  ({result.final_reason})")
    if args.save:
        from app.storage.db import save_disclosure
        rid = save_disclosure(result)
        print(f"💾 저장됨 (id={rid}) → data/quantinue.sqlite")
    if result.notes:
        print("📝 notes:")
        for n in result.notes:
            print(f"   - {n}")


if __name__ == "__main__":
    main()

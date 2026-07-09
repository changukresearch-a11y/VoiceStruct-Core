"""disclosure_ref(뉴스 #10, 명세 최최종 2026-07-09) 스모크 테스트 — 격리 DB.

뉴스 대표 event_type ↔ 같은 종목 오늘 공시 filing_no 매칭 신설 필드 검증.
실행: `python tests/test_disclosure_ref.py` (pytest 불필요, 기존 verify_spec 관례).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from datetime import datetime, timezone

# 프로젝트 루트(quantinue/)를 import 경로에 (하드코딩 없이 상대 계산)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:                                     # Windows 콘솔(cp949)에서도 이모지 출력
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.storage import db
db._DB = Path(tempfile.mkdtemp()) / "test.sqlite"     # 실 DB 오염 방지(격리)

from app.scheduler.bundle_snapshot import BundleAccumulator
from app.common.analysis_bundle import build_news_bundle
from app.storage.db import save_news_bundle, latest_news


def _disc(event_type, importance, accession):
    """가짜 DisclosureResult (accumulator가 보는 최소 형태)."""
    return NS(signal=NS(event_type=event_type, importance=importance),
              item=NS(meta={"accession_no": accession}),
              final_permission="WATCH_ONLY", final_reason=None)


def _news(event_type, importance, title, source="reuters.com", trust=0.9, conf=True):
    """가짜 NewsResult (build_news_bundle이 요구하는 속성 충족)."""
    sig = NS(event_type=event_type, sentiment="positive", importance=importance,
             risk_score=1.0, source_trust=trust, is_confirmed=conf,
             certainty_level="High", reason="r", summary="s", keywords=["k"])
    item = NS(title=title, meta={"source": source}, published_at=None, url="http://x")
    return NS(signal=sig, item=item, final_permission="WATCH_ONLY",
              final_reason=None, source_grade="ALLOW", dropped=False)


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    assert cond, name


def main() -> None:
    acc = BundleAccumulator(trade_date="2026-07-09")

    print("[1] disclosure_ref_for 단위")
    acc.add_disclosure("AAPL", "0000-24-1", _disc("earnings", 8, "0000-24-1"))
    acc.add_disclosure("AAPL", "0000-24-2", _disc("earnings", 9, "0000-24-2"))  # imp 최대
    acc.add_disclosure("AAPL", "0000-24-3", _disc("ma", 5, "0000-24-3"))
    check("earnings → importance 최대(0000-24-2)",
          acc.disclosure_ref_for("AAPL", "earnings") == "0000-24-2")
    check("ma → 0000-24-3", acc.disclosure_ref_for("AAPL", "ma") == "0000-24-3")
    check("매칭 공시 없는 event_type → None",
          acc.disclosure_ref_for("AAPL", "buyback") is None)
    check("other는 매칭 제외 → None", acc.disclosure_ref_for("AAPL", "other") is None)
    check("None event_type → None", acc.disclosure_ref_for("AAPL", None) is None)
    check("공시 없는 종목 → None", acc.disclosure_ref_for("TSLA", "earnings") is None)

    print("[2] 전체 번들 빌드 + 스케줄러식 주입")
    acc.add_news("AAPL", "n1", _news("earnings", 8, "Apple Q2 beats"))
    nb = build_news_bundle("AAPL", "2026-07-09", news_results=acc.news_for("AAPL"))
    check("뉴스 대표 event_type=earnings", nb.event_type == "earnings")
    check("기본값 disclosure_ref=None(주입 전)", nb.disclosure_ref is None)
    if nb.has_signal:
        nb.disclosure_ref = acc.disclosure_ref_for("AAPL", nb.event_type)
    check("주입 후 disclosure_ref=0000-24-2", nb.disclosure_ref == "0000-24-2")
    prompt = nb.to_prompt()
    check("to_prompt에 '공식공시 뒷받침' 표기",
          "공식공시 뒷받침" in prompt and "0000-24-2" in prompt)

    print("[3] DB 왕복 (tb_news append → latest_news)")
    nb.collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_news_bundle(nb)
    row = latest_news("AAPL")
    check("latest_news에서 disclosure_ref 읽힘",
          row is not None and row["disclosure_ref"] == "0000-24-2")

    print("[4] has_signal=0(빈 행)은 disclosure_ref 안 채움")
    empty = build_news_bundle("NFLX", "2026-07-09", news_results=[])
    check("빈 뉴스 has_signal=0", empty.has_signal == 0)
    check("빈 뉴스 disclosure_ref=None", empty.disclosure_ref is None)

    print("\n🎉 전부 통과")


if __name__ == "__main__":
    main()

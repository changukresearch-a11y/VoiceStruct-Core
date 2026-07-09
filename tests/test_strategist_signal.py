"""Strategist 압축 신호 스모크 — 개명·peak·hard_block 사유·DB 경로."""
from __future__ import annotations
import sys, tempfile, json
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.storage import db
db._DB = Path(tempfile.mkdtemp()) / "sig.sqlite"

from app.common.analysis_bundle import (
    DisclosureBundle, build_news_bundle)
from app.storage.db import (save_disclosure_bundle, save_news_bundle,
                            latest_disclosure_signal, latest_news_signal)


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    assert cond, name


def news_res(et, imp, senti, title, trust=0.9, conf=True, grade="ALLOW"):
    sig = NS(event_type=et, sentiment=senti, importance=imp, risk_score=1.0,
             source_trust=trust, is_confirmed=conf, certainty_level="High",
             reason="r", summary="s", keywords=["k"])
    item = NS(title=title, meta={"source": "reuters.com"}, published_at=None, url="http://x")
    return NS(signal=sig, item=item, final_permission="WATCH_ONLY",
              final_reason=None, source_grade=grade, dropped=False)


print("[1] 공시 압축 신호 — 필드·개명")
db_ = DisclosureBundle(ticker="AAPL", trade_date="2026-07-09")
db_.has_signal = 1
db_.event_type = "earnings"; db_.importance = 0.82; db_.sentiment_score = 0.76
db_.risk_score = 0.18; db_.hard_block = 0; db_.summary = "매출·이익 개선 확인"
s = db_.to_strategist_signal()
print("     ", json.dumps(s, ensure_ascii=False))
check("importance→importance_score 개명", "importance_score" in s and "importance" not in s)
check("importance_score=0.82", s["importance_score"] == 0.82)
check("핵심 7필드만", set(s) == {"has_signal", "event_type", "importance_score",
      "sentiment_score", "risk_score", "hard_block", "summary"})
check("filing_no·reason·confidence 등 미포함", "filing_no" not in s and "confidence" not in s)

print("[2] hard_block 사유가 summary에 포함")
db2 = DisclosureBundle(ticker="XYZ", trade_date="2026-07-09")
db2.has_signal = 1; db2.event_type = "delisting_halt"; db2.importance = 0.9
db2.sentiment_score = 0.05; db2.risk_score = 0.9; db2.hard_block = 1
db2.hard_block_reason = "going concern"; db2.summary = "상폐 위험 공시"
s2 = db2.to_strategist_signal()
check("hard_block=True", s2["hard_block"] is True)
check(f"summary에 차단 사유 포함: {s2['summary']}",
      "going concern" in s2["summary"] and "차단" in s2["summary"])

print("[3] 뉴스 압축 신호 — peak_importance·trust_score 개명")
nb = build_news_bundle("NVDA", "2026-07-09",
                       news_results=[news_res("earnings", 8, "positive", "beat"),
                                     news_res("guidance_change", 6, "positive", "raise")])
ns = nb.to_strategist_signal()
print("     ", json.dumps(ns, ensure_ascii=False))
check("peak_importance 포함", "peak_importance" in ns)
check("source_trust→trust_score 개명", "trust_score" in ns and "source_trust" not in ns)
check("importance_score 개명", "importance_score" in ns)
check("article_count = 기사 수", ns["article_count"] == 2)
check("peak ≥ importance (강신호 보존)", ns["peak_importance"] >= ns["importance_score"])

print("[4] 신호 없음 → has_signal=false + hard_block만")
empty = build_news_bundle("TSLA", "2026-07-09", news_results=[]).to_strategist_signal()
check("빈 뉴스 has_signal=False", empty["has_signal"] is False)
check("빈 뉴스 점수 필드 없음", "importance_score" not in empty)
check("빈 뉴스도 hard_block 포함", empty["hard_block"] is False)

print("[5] DB 경로 — 최신 행에서 압축 신호 (Strategist 실제 경로)")
db_.collected_at = "2026-07-09T10:00:00+00:00"; save_disclosure_bundle(db_)
nb.collected_at = "2026-07-09T10:00:00+00:00"; save_news_bundle(nb)
ds = latest_disclosure_signal("AAPL")
nsig = latest_news_signal("NVDA")
check("latest_disclosure_signal 압축 반환", ds["event_type"] == "earnings" and ds["importance_score"] == 0.82)
check("latest_news_signal peak 포함", "peak_importance" in nsig)
check("없는 종목 → has_signal=False", latest_disclosure_signal("NONE")["has_signal"] is False)

print("\n🎉 전부 통과")

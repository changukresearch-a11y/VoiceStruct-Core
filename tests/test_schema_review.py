"""리뷰 반영 스키마 변경 스모크 — is_positive · 단일 _id PK · KST 헬퍼."""
from __future__ import annotations
import sys, shutil, tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.storage import db


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


def cols_of(conn, t):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}

def pk_of(conn, t):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({t})") if r[5]]


print("[1] 새 DB 스키마 — 단일 _id PK · is_positive · UNIQUE")
db._DB = Path(tempfile.mkdtemp()) / "new.sqlite"
from app.common.analysis_bundle import build_news_bundle, build_disclosure_bundle
from app.storage.db import save_news_bundle, save_disclosure_bundle, latest_news, to_kst
conn = db._conn()
for t in ("tb_disclosure", "tb_news"):
    c = cols_of(conn, t)
    check(f"{t} _id 존재", "_id" in c)
    check(f"{t} is_positive 존재", "is_positive" in c)
    check(f"{t} PK = [_id]", pk_of(conn, t) == ["_id"])
    uniq = any(r[2] for r in conn.execute(f"PRAGMA index_list({t})"))
    check(f"{t} UNIQUE 인덱스 존재", uniq)
conn.close()

print("[2] is_positive 계산 (sentiment_score>0.5)")
# 호재 뉴스 → is_positive=1
nb = build_news_bundle("NVDA", "2026-07-02",
                       news_results=[news_res("earnings", 8, "positive", "NVDA beats")])
check(f"호재 뉴스 sentiment_score>0.5 → is_positive=True (score={nb.sentiment_score})",
      nb.is_positive is True and nb.sentiment_score > 0.5)
# 악재 뉴스 → is_positive=0
nb2 = build_news_bundle("XYZ", "2026-07-02",
                        news_results=[news_res("regulation_legal", 9, "negative", "XYZ lawsuit")])
check(f"악재 뉴스 → is_positive=False (score={nb2.sentiment_score})",
      nb2.is_positive is False)
# 신호 없음 → is_positive=False
empty = build_news_bundle("TSLA", "2026-07-02", news_results=[])
check("빈 뉴스 → is_positive=False", empty.is_positive is False)

print("[3] 저장 → _id 자동증가 · is_positive 왕복 · UNIQUE REPLACE")
nb.collected_at = "2026-07-02T10:05:00+00:00"
save_news_bundle(nb)
nb_b = build_news_bundle("NVDA", "2026-07-02",
                         news_results=[news_res("earnings", 6, "positive", "NVDA 2")])
nb_b.collected_at = "2026-07-02T10:10:00+00:00"
save_news_bundle(nb_b)
conn = db._conn()
rows = conn.execute("SELECT _id, ticker, collected_at, is_positive FROM tb_news ORDER BY _id").fetchall()
check(f"2행 저장·_id 자동증가 {[r[0] for r in rows]}", [r[0] for r in rows] == [1, 2])
check("is_positive가 1로 저장됨", rows[0][3] == 1)
# 같은 (ticker, collected_at) 재저장 → UNIQUE 충돌 REPLACE (행 수 유지)
save_news_bundle(nb)   # collected_at 10:05 동일
n = conn.execute("SELECT COUNT(*) FROM tb_news").fetchone()[0]
check(f"UNIQUE 재저장 시 행 수 유지 (={n})", n == 2)
conn.close()

print("[4] KST 표시 헬퍼 (저장은 UTC)")
check("UTC→KST +9h", to_kst("2026-07-02T10:05:00+00:00") == "2026-07-02T19:05:00+09:00")
check("Z 표기도 처리", to_kst("2026-07-02T10:05:00Z") == "2026-07-02T19:05:00+09:00")
check("None 안전", to_kst(None) is None)

print("[5] 실 DB 복사본 마이그레이션 (복합PK → 단일 _id 재생성, 데이터 보존)")
real = Path("C:/Users/user/Desktop/claude/quantinue/data/quantinue.sqlite")
if real.exists():
    tmp = Path(tempfile.mkdtemp()) / "real_copy.sqlite"
    shutil.copy(real, tmp)
    db._DB = tmp
    import sqlite3
    pre = sqlite3.connect(tmp)
    had_id = "_id" in cols_of(pre, "tb_news")
    n_before = pre.execute("SELECT COUNT(*) FROM tb_news").fetchone()[0]
    pre.close()
    conn = db._conn()   # 마이그레이션 실행
    c = cols_of(conn, "tb_news")
    n_after = conn.execute("SELECT COUNT(*) FROM tb_news").fetchone()[0]
    check(f"마이그레이션 후 _id 존재 (이전 있었나={had_id})", "_id" in c)
    check("마이그레이션 후 is_positive 존재", "is_positive" in c)
    check(f"기존 데이터 보존 ({n_before}→{n_after}행)", n_after == n_before)
    check("PK = [_id]", pk_of(conn, "tb_news") == ["_id"])
    conn.close()
else:
    print("  (실 DB 없음 — 마이그레이션 테스트 skip)")

print("\n🎉 전부 통과")

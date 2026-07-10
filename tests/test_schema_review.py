"""스키마 스모크 — _score 통일 개명 · is_positive 삭제 · 단일 _id PK · KST 헬퍼."""
from __future__ import annotations
import sys, shutil, tempfile
from pathlib import Path
from types import SimpleNamespace as NS

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


print("[1] 새 DB 스키마 — 단일 _id PK · _score 통일 · is_positive 없음 · UNIQUE")
db._DB = Path(tempfile.mkdtemp()) / "new.sqlite"
from app.common.analysis_bundle import build_news_bundle, build_disclosure_bundle
from app.storage.db import save_news_bundle, save_disclosure_bundle, latest_news, to_kst
conn = db._conn()
for t in ("tb_disclosure", "tb_news"):
    c = cols_of(conn, t)
    check(f"{t} _id 존재", "_id" in c)
    check(f"{t} is_positive 삭제됨", "is_positive" not in c)
    check(f"{t} importance_score·confidence_score 개명", {"importance_score", "confidence_score"} <= c)
    check(f"{t} 구 컬럼(importance/confidence) 없음", "importance" not in c and "confidence" not in c)
    check(f"{t} PK = [_id]", pk_of(conn, t) == ["_id"])
    uniq = any(r[2] for r in conn.execute(f"PRAGMA index_list({t})"))
    check(f"{t} UNIQUE 인덱스 존재", uniq)
check("tb_news trust_score·peak_importance_score 개명", {"trust_score", "peak_importance_score"} <= cols_of(conn, "tb_news"))
check("tb_news 구 source_trust/peak_importance 없음", "source_trust" not in cols_of(conn, "tb_news") and "peak_importance" not in cols_of(conn, "tb_news"))
conn.close()

print("[2] 개명 필드 산출 (0~1 · is_positive 부재)")
nb = build_news_bundle("NVDA", "2026-07-02",
                       news_results=[news_res("earnings", 8, "positive", "NVDA beats")])
check(f"importance_score 0~1 (={nb.importance_score})", 0.0 <= nb.importance_score <= 1.0)
check(f"trust_score 0~1 (={nb.trust_score})", 0.0 <= nb.trust_score <= 1.0)
check(f"peak_importance_score ≥ importance_score (={nb.peak_importance_score})",
      nb.peak_importance_score >= nb.importance_score)
check("NewsBundle에 is_positive 필드 없음", "is_positive" not in nb.model_fields)
db_b = build_disclosure_bundle("NVDA", "2026-07-02")
check("DisclosureBundle에 is_positive 필드 없음", "is_positive" not in db_b.model_fields)
check("DisclosureBundle importance_score·confidence_score 존재",
      "importance_score" in db_b.model_fields and "confidence_score" in db_b.model_fields)

print("[3] 저장 → _id 자동증가 · importance_score 왕복 · UNIQUE REPLACE")
nb.collected_at = "2026-07-02T10:05:00+00:00"
save_news_bundle(nb)
nb_b = build_news_bundle("NVDA", "2026-07-02",
                         news_results=[news_res("earnings", 6, "positive", "NVDA 2")])
nb_b.collected_at = "2026-07-02T10:10:00+00:00"
save_news_bundle(nb_b)
conn = db._conn()
rows = conn.execute("SELECT _id, ticker, collected_at, importance_score FROM tb_news ORDER BY _id").fetchall()
check(f"2행 저장·_id 자동증가 {[r[0] for r in rows]}", [r[0] for r in rows] == [1, 2])
check(f"importance_score 왕복 저장 (={rows[0][3]})", abs(rows[0][3] - nb.importance_score) < 1e-9)
save_news_bundle(nb)   # collected_at 10:05 동일
n = conn.execute("SELECT COUNT(*) FROM tb_news").fetchone()[0]
check(f"UNIQUE 재저장 시 행 수 유지 (={n})", n == 2)
conn.close()

print("[4] KST 표시 헬퍼 (저장은 UTC)")
check("UTC→KST +9h", to_kst("2026-07-02T10:05:00+00:00") == "2026-07-02T19:05:00+09:00")
check("Z 표기도 처리", to_kst("2026-07-02T10:05:00Z") == "2026-07-02T19:05:00+09:00")
check("None 안전", to_kst(None) is None)

print("[5] 실 DB 복사본 마이그레이션 (구 컬럼·is_positive → _score 재생성, 데이터 보존)")
real = Path("C:/Users/user/Desktop/claude/quantinue/data/quantinue.sqlite")
if real.exists():
    tmp = Path(tempfile.mkdtemp()) / "real_copy.sqlite"
    shutil.copy(real, tmp)
    db._DB = tmp
    import sqlite3
    pre = sqlite3.connect(tmp)
    n_before = pre.execute("SELECT COUNT(*) FROM tb_news").fetchone()[0]
    pre.close()
    conn = db._conn()   # 마이그레이션 실행
    c = cols_of(conn, "tb_news")
    n_after = conn.execute("SELECT COUNT(*) FROM tb_news").fetchone()[0]
    check("마이그레이션 후 importance_score 존재", "importance_score" in c)
    check("마이그레이션 후 is_positive 삭제", "is_positive" not in c)
    check(f"기존 데이터 보존 ({n_before}→{n_after}행)", n_after == n_before)
    check("PK = [_id]", pk_of(conn, "tb_news") == ["_id"])
    conn.close()
else:
    print("  (실 DB 없음 — 마이그레이션 테스트 skip)")

print("\n🎉 전부 통과")

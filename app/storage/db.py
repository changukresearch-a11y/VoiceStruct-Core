"""
SQLite 저장 레이어 (백테스트 토대).

모든 공시 판단을 기록한다. return_1d/3d/5d, outcome 컬럼은 나중에
시장반응·성과를 채워 넣기 위한 자리(메모리: 백테스트 피드백).

DB는 MVP 단계라 SQLite. (확장 시 Postgres+TimescaleDB는 미정)
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DB = Path(__file__).resolve().parents[2] / "data" / "quantinue.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS disclosure_signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  analyzed_at TEXT NOT NULL,
  filed_at TEXT,
  ticker TEXT, form_type TEXT, item_no TEXT, fiscal TEXT,
  event_type TEXT, sentiment TEXT, importance INTEGER, risk_score REAL,
  certainty TEXT,
  hard_risk_flag INTEGER, hard_risk_type TEXT,
  llm_permission TEXT, final_permission TEXT, final_reason TEXT,
  reason TEXT, verdict TEXT, summary TEXT, keywords TEXT,
  accession_no TEXT, accepted_at TEXT, title TEXT, url TEXT,
  return_1d REAL, return_3d REAL, return_5d REAL, outcome TEXT
);

CREATE TABLE IF NOT EXISTS processed_filings (
  accession TEXT PRIMARY KEY,
  ticker TEXT, form_type TEXT, processed_at TEXT
);

CREATE TABLE IF NOT EXISTS news_signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  analyzed_at TEXT NOT NULL,
  ticker TEXT,
  news_key TEXT UNIQUE,          -- dedup 키 (google_link 우선)
  source TEXT, source_grade TEXT,
  title TEXT, url TEXT, published_at TEXT,
  keyword_result TEXT, keyword_category TEXT,
  dropped INTEGER,
  event_type TEXT, sentiment TEXT, importance INTEGER, risk_score REAL,
  certainty TEXT, is_confirmed INTEGER, source_trust REAL,
  llm_permission TEXT, final_permission TEXT, final_reason TEXT, reason TEXT,
  verdict TEXT, summary TEXT, keywords TEXT,
  return_1d REAL, return_3d REAL, return_5d REAL, outcome TEXT
);

-- ── Strategist 전달 계약: 번들 스냅샷 (팀 명세 tb_disclosure/tb_news) ──
-- 위 *_signals(per-signal 분석로그, 스케줄러·백테스트용)와 별개.
-- 여기엔 DisclosureBundle/NewsBundle(전략가가 읽는 출력)을 시계열로 append.
-- PK=(ticker, collected_at): 새 공시/기사 뜰 때마다 새 행, Strategist는 최신 행.
CREATE TABLE IF NOT EXISTS tb_disclosure (
  ticker TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  trade_date TEXT,
  has_signal INTEGER,
  filing_title TEXT, filing_no TEXT, filed_at TEXT,
  event_type TEXT, sentiment TEXT, sentiment_score REAL, reason TEXT,
  importance REAL, risk_score REAL, confidence REAL,
  hard_block INTEGER, hard_block_reason TEXT,
  summary TEXT, keywords TEXT,
  PRIMARY KEY (ticker, collected_at)
);

CREATE TABLE IF NOT EXISTS tb_news (
  ticker TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  trade_date TEXT,
  has_signal INTEGER,
  news_title TEXT, source TEXT, published_at TEXT,
  news_count INTEGER, news_confirmed INTEGER, news_rumor INTEGER,
  event_type TEXT, sentiment TEXT, sentiment_score REAL, reason TEXT,
  importance REAL, peak_importance REAL, risk_score REAL, confidence REAL,
  source_trust REAL, grade_score REAL, confirmed_score REAL, fact_check TEXT,
  hard_block INTEGER, hard_block_reason TEXT,
  top_evidence TEXT, summary TEXT, keywords TEXT, ref TEXT,
  PRIMARY KEY (ticker, collected_at)
);
"""

# 번들 스냅샷 테이블 컬럼(모델 필드 순서와 동일). keywords/top_evidence는 TEXT로 접어 저장.
_TB_DISC_COLS = [
    "ticker", "collected_at", "trade_date", "has_signal",
    "filing_title", "filing_no", "filed_at",
    "event_type", "sentiment", "sentiment_score", "reason",
    "importance", "risk_score", "confidence",
    "hard_block", "hard_block_reason", "summary", "keywords",
]

_TB_NEWS_COLS = [
    "ticker", "collected_at", "trade_date", "has_signal",
    "news_title", "source", "published_at",
    "news_count", "news_confirmed", "news_rumor",
    "event_type", "sentiment", "sentiment_score", "reason",
    "importance", "peak_importance", "risk_score", "confidence",
    "source_trust", "grade_score", "confirmed_score", "fact_check",
    "hard_block", "hard_block_reason", "top_evidence", "summary", "keywords", "ref",
]

_NEWS_COLS = [
    "analyzed_at", "ticker", "news_key", "source", "source_grade",
    "title", "url", "published_at", "keyword_result", "keyword_category",
    "dropped", "event_type", "sentiment", "importance", "risk_score",
    "certainty", "is_confirmed", "source_trust",
    "llm_permission", "final_permission", "final_reason", "reason",
    "verdict", "summary", "keywords",
]

_COLS = [
    "analyzed_at", "filed_at", "ticker", "form_type", "item_no", "fiscal",
    "event_type", "sentiment", "importance", "risk_score", "certainty",
    "hard_risk_flag", "hard_risk_type",
    "llm_permission", "final_permission", "final_reason",
    "reason", "verdict", "summary", "keywords",
    "accession_no", "accepted_at", "title", "url",
]


def _migrate(conn: sqlite3.Connection) -> None:
    """기존 DB에 없는 컬럼을 보강(ADD COLUMN). CREATE IF NOT EXISTS로는 안 붙음."""
    def _cols(t: str) -> set:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
    dcols = _cols("disclosure_signals")
    for c in ("filed_at", "accepted_at", "title"):   # 공시 원문 식별 보강
        if c not in dcols:
            conn.execute(f"ALTER TABLE disclosure_signals ADD COLUMN {c} TEXT")
    # 요약·키워드·판정 (두 테이블 공통) — 기존 DB 보강
    for t in ("disclosure_signals", "news_signals"):
        existing = _cols(t)
        for c in ("verdict", "summary", "keywords"):
            if c not in existing:
                conn.execute(f"ALTER TABLE {t} ADD COLUMN {c} TEXT")


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB)
    conn.executescript(_SCHEMA)   # _SCHEMA는 여러 CREATE 문
    _migrate(conn)
    return conn


def save_disclosure(result: Any) -> int:
    """DisclosureResult 1건을 저장하고 row id를 반환."""
    sig = result.signal
    hr = result.hard_risk
    meta = result.item.meta

    row = {
        "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "filed_at": meta.get("filed_at"),
        "ticker": result.item.ticker,
        "form_type": meta.get("form_type"),
        "item_no": meta.get("item_no"),
        "fiscal": meta.get("fiscal"),
        "event_type": getattr(sig, "event_type", None),
        "sentiment": getattr(sig, "sentiment", None),
        "importance": getattr(sig, "importance", None),
        "risk_score": getattr(sig, "risk_score", None),
        "certainty": getattr(sig, "certainty_level", None),
        "hard_risk_flag": int(bool(hr)),
        "hard_risk_type": hr.risk_type if hr else None,
        "llm_permission": getattr(sig, "trade_permission", None),  # LLM 원본
        "final_permission": result.final_permission,
        "final_reason": result.final_reason,
        "reason": getattr(sig, "reason", None),
        "verdict": getattr(sig, "verdict", None),
        "summary": getattr(sig, "summary", None),
        "keywords": ", ".join(getattr(sig, "keywords", []) or []) or None,
        "accession_no": meta.get("accession_no"),
        "accepted_at": meta.get("accepted_at"),
        "title": result.item.title,
        "url": result.item.url,
    }
    placeholders = ", ".join("?" for _ in _COLS)
    with _conn() as conn:
        cur = conn.execute(
            f"INSERT INTO disclosure_signals ({', '.join(_COLS)}) "
            f"VALUES ({placeholders})",
            [row[c] for c in _COLS],
        )
        return cur.lastrowid


def is_filing_processed(accession: str | None) -> bool:
    """이 accession을 이미 분석·저장했는지 (form 무관 증분 판정)."""
    if not accession:
        return False
    with _conn() as conn:
        r = conn.execute(
            "SELECT 1 FROM processed_filings WHERE accession=?",
            (accession,)).fetchone()
    return r is not None


def mark_filing_processed(accession: str | None, ticker: str,
                          form_type: str) -> None:
    """accession을 처리 완료로 기록 (같은 공시 재분석 방지)."""
    if not accession:
        return
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_filings "
            "(accession, ticker, form_type, processed_at) VALUES (?,?,?,?)",
            (accession, ticker.upper(), form_type,
             datetime.now(timezone.utc).isoformat(timespec="seconds")))


def recent(limit: int = 10) -> list[sqlite3.Row]:
    """최근 저장된 신호 조회 (확인용)."""
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id, analyzed_at, ticker, form_type, event_type, sentiment, "
            "importance, final_permission FROM disclosure_signals "
            "ORDER BY id DESC LIMIT ?", (limit,))
        return cur.fetchall()


# ── 뉴스 저장 + DB 기반 dedup (스케줄러 재시작에도 유지) ──────────────

def news_dedup_key(item: Any) -> str:
    """뉴스 dedup 키. 기사별 유니크한 google_link 우선(도메인 url은 부정확)."""
    meta = getattr(item, "meta", {}) or {}
    return meta.get("google_link") or item.url or item.title


def is_news_seen(news_key: str | None) -> bool:
    """이 뉴스를 이미 처리·저장했는지 (재분석/재LLM 방지)."""
    if not news_key:
        return False
    with _conn() as conn:
        r = conn.execute(
            "SELECT 1 FROM news_signals WHERE news_key=?", (news_key,)).fetchone()
    return r is not None


def save_news(result: Any) -> int | None:
    """NewsResult 1건을 저장(드롭 포함)하고 row id 반환. 중복키면 None."""
    item = result.item
    sig = result.signal
    kv = result.keyword_verdict
    meta = item.meta or {}
    pub = item.published_at.isoformat() if item.published_at else None

    row = {
        "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ticker": item.ticker,
        "news_key": news_dedup_key(item),
        "source": meta.get("source"),
        "source_grade": result.source_grade,
        "title": item.title,
        "url": item.url,
        "published_at": pub,
        "keyword_result": getattr(kv, "result", None),
        "keyword_category": getattr(kv, "category", None),
        "dropped": int(bool(result.dropped)),
        "event_type": getattr(sig, "event_type", None),
        "sentiment": getattr(sig, "sentiment", None),
        "importance": getattr(sig, "importance", None),
        "risk_score": getattr(sig, "risk_score", None),
        "certainty": getattr(sig, "certainty_level", None),
        "is_confirmed": (int(sig.is_confirmed) if sig is not None else None),
        "source_trust": getattr(sig, "source_trust", None),
        "llm_permission": getattr(sig, "trade_permission", None),
        "final_permission": result.final_permission,
        "final_reason": result.final_reason,
        "reason": getattr(sig, "reason", None),
        "verdict": getattr(sig, "verdict", None),
        "summary": getattr(sig, "summary", None),
        "keywords": ", ".join(getattr(sig, "keywords", []) or []) or None,
    }
    placeholders = ", ".join("?" for _ in _NEWS_COLS)
    with _conn() as conn:
        cur = conn.execute(
            f"INSERT OR IGNORE INTO news_signals ({', '.join(_NEWS_COLS)}) "
            f"VALUES ({placeholders})",
            [row[c] for c in _NEWS_COLS],
        )
        return cur.lastrowid if cur.rowcount else None


def recent_news(limit: int = 10) -> list[sqlite3.Row]:
    """최근 저장된 뉴스 신호 조회 (확인용)."""
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id, analyzed_at, ticker, source, source_grade, dropped, "
            "event_type, sentiment, final_permission, title FROM news_signals "
            "ORDER BY id DESC LIMIT ?", (limit,))
        return cur.fetchall()


# ── Strategist 전달 계약: 번들 스냅샷 저장/읽기 (tb_disclosure/tb_news) ──
# per-signal 로그(save_disclosure/save_news)와 별개. 여기엔 완성된 번들을
# 시계열로 append하고, Strategist는 종목별 최신 행을 읽는다.

def _bundle_row(bundle: Any, cols: list[str]) -> dict[str, Any]:
    """번들(Pydantic)을 테이블 컬럼 dict로. 리스트 필드는 TEXT로 접는다."""
    d = bundle.model_dump()
    row: dict[str, Any] = {}
    for c in cols:
        v = d.get(c)
        if c == "keywords":
            v = ", ".join(v) if v else None
        elif c == "top_evidence":
            v = " | ".join(v) if v else None
        row[c] = v
    return row


def _save_bundle(table: str, cols: list[str], bundle: Any) -> None:
    """번들 스냅샷 1행 append. PK=(ticker, collected_at) 충돌 시 최신값으로 대체."""
    row = _bundle_row(bundle, cols)
    placeholders = ", ".join("?" for _ in cols)
    with _conn() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) "
            f"VALUES ({placeholders})",
            [row[c] for c in cols])


def save_disclosure_bundle(bundle: Any) -> None:
    """DisclosureBundle 스냅샷을 tb_disclosure에 append."""
    _save_bundle("tb_disclosure", _TB_DISC_COLS, bundle)


def save_news_bundle(bundle: Any) -> None:
    """NewsBundle 스냅샷을 tb_news에 append."""
    _save_bundle("tb_news", _TB_NEWS_COLS, bundle)


def latest_disclosure(ticker: str) -> sqlite3.Row | None:
    """종목의 최신 공시 번들 스냅샷 (Strategist 읽기용)."""
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM tb_disclosure WHERE ticker=? "
            "ORDER BY collected_at DESC LIMIT 1", (ticker.upper(),)).fetchone()


def latest_news(ticker: str) -> sqlite3.Row | None:
    """종목의 최신 뉴스 번들 스냅샷 (Strategist 읽기용)."""
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM tb_news WHERE ticker=? "
            "ORDER BY collected_at DESC LIMIT 1", (ticker.upper(),)).fetchone()


# ── 백테스트: 전방수익률 채우기 대상/기록 ────────────────────────────
# 신호 발생일(day 0) 기준 컬럼: 공시=analyzed_at(정확한 filed_at은 후속),
# 뉴스=published_at 우선.

_RETURN_TABLES = {"disclosure_signals", "news_signals"}


def _base_date_expr(table: str) -> str:
    # day 0 = 실제 이벤트일 우선(공시 filed_at / 뉴스 published_at), 없으면 analyzed_at
    return ("COALESCE(published_at, analyzed_at)"
            if table == "news_signals" else "COALESCE(filed_at, analyzed_at)")


def pending_returns(table: str, before_date: str | None = None) -> list[sqlite3.Row]:
    """아직 수익률 미확정(return_5d IS NULL)인 신호. before_date(YYYY-MM-DD) 이하만."""
    if table not in _RETURN_TABLES:
        raise ValueError(f"허용되지 않은 테이블: {table}")
    bexpr = _base_date_expr(table)
    sql = (f"SELECT id, ticker, {bexpr} AS base_date, sentiment, event_type "
           f"FROM {table} WHERE return_5d IS NULL AND ticker IS NOT NULL")
    params: list = []
    if before_date:
        sql += f" AND substr({bexpr}, 1, 10) <= ?"
        params.append(before_date)
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, params).fetchall()


def set_returns(table: str, row_id: int, r1: float | None, r3: float | None,
                r5: float | None, outcome: str | None = None) -> None:
    if table not in _RETURN_TABLES:
        raise ValueError(f"허용되지 않은 테이블: {table}")
    with _conn() as conn:
        conn.execute(
            f"UPDATE {table} SET return_1d=?, return_3d=?, return_5d=?, outcome=? "
            f"WHERE id=?", (r1, r3, r5, outcome, row_id))


def filled_returns(table: str) -> list[sqlite3.Row]:
    """수익률이 채워진 신호(리포트 집계용)."""
    if table not in _RETURN_TABLES:
        raise ValueError(f"허용되지 않은 테이블: {table}")
    extra = ", source_grade" if table == "news_signals" else ""
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            f"SELECT event_type, sentiment{extra}, "
            f"return_1d, return_3d, return_5d, outcome "
            f"FROM {table} WHERE return_5d IS NOT NULL").fetchall()

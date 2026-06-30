"""
유니버스 저장소 — 감시 대상 기업 명단(companies 테이블).

50 → 200 → 2000 점진 확장 전제. priority/active로 어떤 종목을 어떤 순서로
돌릴지 제어하고, last_accession으로 증분 처리(이미 본 공시 skip)를 지원한다.
공시 신호 테이블과 같은 SQLite 파일을 공유.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

_DB = Path(__file__).resolve().parents[2] / "data" / "quantinue.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
  ticker TEXT PRIMARY KEY,
  cik TEXT,
  name TEXT,
  market_cap REAL,
  sector TEXT,
  priority INTEGER DEFAULT 100,
  active INTEGER DEFAULT 1,
  last_accession TEXT,
  last_processed_at TEXT
);
"""


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB)
    conn.execute(_SCHEMA)
    return conn


def upsert_company(ticker: str, cik: str, name: str,
                   priority: int = 100) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO companies (ticker, cik, name, priority) VALUES (?,?,?,?) "
            "ON CONFLICT(ticker) DO UPDATE SET cik=excluded.cik, name=excluded.name",
            (ticker.upper(), cik, name, priority))


def get_active_tickers(limit: int = 50) -> list[str]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT ticker FROM companies WHERE active=1 "
            "ORDER BY priority, ticker LIMIT ?", (limit,)).fetchall()
    return [r[0] for r in rows]


def count() -> int:
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]


def get_last_accession(ticker: str) -> str | None:
    with _conn() as conn:
        r = conn.execute(
            "SELECT last_accession FROM companies WHERE ticker=?",
            (ticker.upper(),)).fetchone()
    return r[0] if r else None


def mark_processed(ticker: str, accession: str | None, at: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE companies SET last_accession=?, last_processed_at=? WHERE ticker=?",
            (accession, at, ticker.upper()))

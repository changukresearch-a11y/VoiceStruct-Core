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
  ticker TEXT, form_type TEXT, item_no TEXT, fiscal TEXT,
  event_type TEXT, sentiment TEXT, importance INTEGER, risk_score REAL,
  certainty TEXT,
  hard_risk_flag INTEGER, hard_risk_type TEXT,
  llm_permission TEXT, final_permission TEXT, final_reason TEXT,
  reason TEXT, accession_no TEXT, url TEXT,
  return_1d REAL, return_3d REAL, return_5d REAL, outcome TEXT
);
"""

_COLS = [
    "analyzed_at", "ticker", "form_type", "item_no", "fiscal",
    "event_type", "sentiment", "importance", "risk_score", "certainty",
    "hard_risk_flag", "hard_risk_type",
    "llm_permission", "final_permission", "final_reason",
    "reason", "accession_no", "url",
]


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB)
    conn.execute(_SCHEMA)
    return conn


def save_disclosure(result: Any) -> int:
    """DisclosureResult 1건을 저장하고 row id를 반환."""
    sig = result.signal
    hr = result.hard_risk
    meta = result.item.meta

    row = {
        "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
        "accession_no": meta.get("accession_no"),
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


def recent(limit: int = 10) -> list[sqlite3.Row]:
    """최근 저장된 신호 조회 (확인용)."""
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id, analyzed_at, ticker, form_type, event_type, sentiment, "
            "importance, final_permission FROM disclosure_signals "
            "ORDER BY id DESC LIMIT ?", (limit,))
        return cur.fetchall()

"""
하드리스크 정책 — 본문 키워드 검사로 자동매매 안전장치 적용.

LLM 호출과 무관하게(또는 그 결과를 덮어써서) 위험 구간 매수를 차단한다.
'수익 기회 찾기'가 아니라 '절대 진입하면 안 되는 구간 막기'가 목적.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CONFIG = Path(__file__).resolve().parents[2] / "config" / "hard_risk_policy.yaml"


@dataclass
class HardRiskHit:
    risk_type: str          # 예: "delisting"
    trade_permission: str   # 예: "BLOCK_BUY"
    risk_score_min: float
    matched_keyword: str


@lru_cache(maxsize=1)
def _load_rules() -> dict[str, Any]:
    with _CONFIG.open(encoding="utf-8") as f:
        return yaml.safe_load(f)["hard_risk_events"]


def check_hard_risk(text: str) -> HardRiskHit | None:
    """본문에서 하드리스크 키워드를 찾으면 첫 매치를 반환, 없으면 None."""
    low = text.lower()
    for risk_type, rule in _load_rules().items():
        for kw in rule["keywords"]:
            if kw.lower() in low:
                return HardRiskHit(
                    risk_type=risk_type,
                    trade_permission=rule["trade_permission"],
                    risk_score_min=float(rule["risk_score_min"]),
                    matched_keyword=kw,
                )
    return None

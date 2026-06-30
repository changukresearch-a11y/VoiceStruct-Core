"""
최종 매매권한 결정 레이어.

하드룰 / LLM 신호 / 8-K Item 기본값을 종합해 최종 trade_permission을 정한다.
원칙(메모리):
  - 여러 소스 중 '가장 보수적인(제한적인)' 권한을 채택 (안전 우선).
  - 시장반응 확인 전에는 매수 계열(TRADE_ELIGIBLE*)을 WATCH_ONLY로 강등.
    (ALLOW≠매수허용 / "공시 떴으니 바로 산다" 금지)
  - 하드룰은 항상 우선(상폐·거래정지·회계·희석 등).
"""
from __future__ import annotations

from typing import Any

from app.policies.hard_risk_policy import HardRiskHit

# 제한도(높을수록 보수적). 종합 시 가장 높은 값을 채택.
RESTRICTIVENESS = {
    "BLOCK_ALL": 6,
    "BLOCK_BUY": 5,
    "RISK_REDUCE": 4,
    "WATCH_ONLY": 3,
    "TRADE_ELIGIBLE_SMALL_SIZE": 2,
    "TRADE_ELIGIBLE": 1,
}
_BUY_TIER = {"TRADE_ELIGIBLE", "TRADE_ELIGIBLE_SMALL_SIZE"}


def _most_restrictive(perms: list[str]) -> str:
    return max(perms, key=lambda p: RESTRICTIVENESS.get(p, 3))


def decide_final_permission(
    hard_risk: HardRiskHit | None,
    signal: Any | None,
    routed_item: dict[str, Any] | None,
    market_confirmed: bool = False,
) -> tuple[str, str]:
    """(final_permission, reason) 반환."""
    candidates: list[str] = []
    parts: list[str] = []

    if hard_risk:
        candidates.append(hard_risk.trade_permission)
        parts.append(f"하드룰:{hard_risk.risk_type}")
    if signal is not None:
        candidates.append(signal.trade_permission)
        parts.append(f"LLM:{signal.event_type}/{signal.trade_permission}")
    if routed_item:
        candidates.append(routed_item["default_permission"])
        parts.append(f"Item{routed_item['item_no']}기본")

    if not candidates:
        return "WATCH_ONLY", "신호 없음 → 기본 관찰"

    final = _most_restrictive(candidates)

    # 시장반응 미확인 시 매수 계열 강등 (MVP는 항상 미확인)
    if not market_confirmed and final in _BUY_TIER:
        final = "WATCH_ONLY"
        parts.append("시장반응 미확인→매수보류")

    return final, " / ".join(parts)

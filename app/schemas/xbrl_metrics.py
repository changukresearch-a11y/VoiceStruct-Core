"""
XBRL 재무 수치 스키마 (10-Q/10-K).

LLM이 '실적 좋다'고 말하게 두지 않고, SEC XBRL의 확정 수치를 코드로 뽑아
YoY 변화율까지 계산한다. 이 객체가 LLM 프롬프트에 주입되어 LLM은
가이던스 뉘앙스만 해석한다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class XbrlMetrics(BaseModel):
    fiscal: str | None = Field(None, description="최신 보고 기간 (예: '2026 Q2').")

    revenue: float | None = None
    revenue_yoy_pct: float | None = None

    operating_income: float | None = None
    operating_income_yoy_pct: float | None = None

    net_income: float | None = None
    net_income_yoy_pct: float | None = None

    eps_diluted: float | None = None
    eps_yoy_pct: float | None = None

    def summary_line(self) -> str:
        """LLM 프롬프트 주입용 한 줄 요약."""
        def fmt(v, pct):
            if v is None:
                return "n/a"
            s = f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.2f}"
            return f"{s} ({pct:+.1f}% YoY)" if pct is not None else s
        return (
            f"[{self.fiscal or '?'}] "
            f"Revenue={fmt(self.revenue, self.revenue_yoy_pct)} | "
            f"OpInc={fmt(self.operating_income, self.operating_income_yoy_pct)} | "
            f"NetInc={fmt(self.net_income, self.net_income_yoy_pct)} | "
            f"EPS={fmt(self.eps_diluted, self.eps_yoy_pct)}"
        )

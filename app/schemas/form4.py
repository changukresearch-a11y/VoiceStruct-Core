"""
Form 4 (내부자 거래) 구조화 스키마 — LLM이 아니라 코드 파싱 결과를 담는다.

transactionCode 의미 (핵심):
  P = 공개시장 매수  → 호재 신호 (자신감)
  S = 공개시장 매도  → 약한 악재 (단 10b5-1 예정매도면 중립)
  A = grant/award    → 중립
  M = 파생/옵션 행사 → 중립
  F = 세금 원천징수 매도 → 중립 (자발적 매도 아님)
  G = 증여, C = 전환 등
"""
from __future__ import annotations

from dataclasses import dataclass, field

BUY_CODES = {"P"}
SELL_CODES = {"S"}
NEUTRAL_CODES = {"A", "M", "F", "G", "C", "X", "I"}


@dataclass
class Form4Transaction:
    code: str
    shares: float
    price: float | None
    acquired_disposed: str        # "A"(취득) / "D"(처분)
    is_derivative: bool = False

    @property
    def value(self) -> float:
        return self.shares * (self.price or 0.0)


@dataclass
class Form4Filing:
    ticker: str
    company_name: str | None
    owner_title: str | None
    is_officer: bool
    is_director: bool
    is_10b5_1: bool
    transactions: list[Form4Transaction] = field(default_factory=list)
    accession_no: str | None = None
    url: str | None = None

    def open_market_buy_value(self) -> float:
        return sum(t.value for t in self.transactions if t.code in BUY_CODES)

    def open_market_sell_value(self) -> float:
        return sum(t.value for t in self.transactions if t.code in SELL_CODES)

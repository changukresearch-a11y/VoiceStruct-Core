"""
Form 4 코드 스코어러 (LLM 미사용).

내부자 거래를 규칙으로 점수화해 DisclosureSignal로 변환한다.
원칙(메모리 V3): 공개시장 매수=호재, 매도=약한 악재, 10b5-1 예정매도/베스팅·세금=중립.
실제 매수 결정은 Strategist 몫이라 trade_permission은 보수적(WATCH_ONLY).
"""
from __future__ import annotations

from app.schemas.disclosure_analysis import DisclosureSignal
from app.schemas.form4 import Form4Filing

_SENIOR = ("ceo", "cfo", "chief", "president")


def _is_senior(title: str | None) -> bool:
    return bool(title) and any(k in title.lower() for k in _SENIOR)


def score_form4(f: Form4Filing) -> DisclosureSignal:
    buy = f.open_market_buy_value()
    sell = f.open_market_sell_value()
    senior = _is_senior(f.owner_title)
    rank = f.is_officer or f.is_director

    if buy > sell and buy > 0:
        sentiment = "positive"
        importance = 5 + (2 if senior else 0) + (1 if buy >= 1_000_000 else 0)
        reason = f"내부자 공개시장 매수 ${buy:,.0f} (자신감 신호)"
    elif sell > buy and sell > 0:
        if f.is_10b5_1:
            sentiment, importance = "neutral", 2
            reason = f"매도 ${sell:,.0f} but 10b5-1 예정매도 → 중립"
        else:
            sentiment = "negative"
            importance = 3 + (1 if senior else 0)
            reason = f"내부자 공개시장 매도 ${sell:,.0f} (약한 악재)"
    else:
        # P/S 없음 = 옵션행사(M)·세금(F)·grant(A) 등 → 중립
        sentiment, importance = "neutral", 2
        reason = "베스팅/옵션행사/세금 관련 거래 → 매매 신호 약함"

    importance = max(0, min(10, importance))
    reasoning = (
        f"보고자={f.owner_title or '내부자'}"
        f"(officer={f.is_officer}, director={f.is_director}, senior={senior}). "
        f"공개시장 매수=${buy:,.0f} / 매도=${sell:,.0f}, 10b5-1={f.is_10b5_1}. "
        f"→ {sentiment}."
    )
    evidence = [
        f"{t.code} {t.shares:.0f}주" + (f" @${t.price:.2f}" if t.price else "")
        for t in f.transactions
    ]

    return DisclosureSignal(
        reasoning=reasoning,
        certainty_level="High",            # 공시라 사실 확정
        event_type="insider_trade",
        sentiment=sentiment,
        importance=importance,
        risk_score=2.0 if sentiment != "negative" else 4.0,
        hard_risk_flag=False,
        trade_permission="WATCH_ONLY",     # 실제 매수 판단은 Strategist 몫
        reason=reason,
        evidence_quotes=evidence[:6],
    )

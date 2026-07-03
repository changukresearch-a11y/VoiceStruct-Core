"""
공시 Walking Skeleton — Form별 한 줄 관통 오케스트레이션.

8-K 경로:
  수집 → Item 라우팅 → 하드룰 → LLM 이벤트 해석
10-Q/10-K 경로:
  XBRL 수치 추출 → (수치 요약) → LLM 수치 해석

Form 종류는 form_type_router가 결정한다(코드/LLM 비중 차등).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.collectors.sec_collector import fetch_latest_8k
from app.collectors.sec_xbrl_collector import fetch_latest_financials
from app.common.schemas import NormalizedItem
from app.decision.trade_permission_policy import decide_final_permission
from app.policies.hard_risk_policy import HardRiskHit, check_hard_risk
from app.router.form_8k_item_router import extract_item_numbers, route_item
from app.router.form_type_router import route_form


@dataclass
class DisclosureResult:
    """파이프라인 1회 실행 결과 (각 단계 산출물 누적)."""
    item: NormalizedItem
    route: dict[str, Any]
    routed_item: dict[str, Any] | None = None   # 8-K Item 라우팅 결과
    metrics: Any = None                          # XbrlMetrics | None
    hard_risk: HardRiskHit | None = None
    signal: Any = None                           # DisclosureSignal | None
    final_permission: str | None = None
    final_reason: str | None = None
    notes: list[str] = field(default_factory=list)


def run_disclosure_pipeline(ticker: str, form_type: str = "8-K",
                            use_sample: bool = True,
                            run_llm: bool = False) -> DisclosureResult:
    route = route_form(form_type)

    # Form 4: 코드 스코어링 전용 경로 (LLM 미사용)
    if route.get("needs_form4"):
        from app.analyzers.form4_scorer import score_form4
        from app.collectors.sec_form4_collector import fetch_latest_form4
        item, filing = fetch_latest_form4(ticker)
        result = DisclosureResult(item=item, route=route)
        result.signal = score_form4(filing)
        result.notes.append("Form 4 코드 스코어링 (LLM 미사용)")
        result.hard_risk = check_hard_risk(item.body)
        result.final_permission, result.final_reason = decide_final_permission(
            result.hard_risk, result.signal, None)
        return result

    # 1) 수집 + 정규화 (Form별 분기)
    if route["needs_xbrl"]:
        item, metrics = fetch_latest_financials(ticker)   # XBRL은 항상 실호출
        result = DisclosureResult(item=item, route=route, metrics=metrics)
        result.notes.append(f"XBRL 경로: {metrics.summary_line()}")
        # 10-Q/K 본문 리스크문구 스캔 (수치 경로는 본문을 안 받으므로 별도 수집).
        # going concern·material weakness 등은 수치로 안 잡혀 → 원문에서 하드룰 검사.
        if not use_sample:
            try:
                from app.collectors.sec_collector import fetch_report_text
                text, rmeta = fetch_report_text(ticker, item.meta["form_type"])
                if rmeta:
                    item.meta.setdefault("accession_no", rmeta.get("accession_no"))
                    if rmeta.get("filed_at"):
                        item.meta["filed_at"] = rmeta["filed_at"]  # 제출일 더 정확
                    if rmeta.get("accepted_at"):
                        item.meta["accepted_at"] = rmeta["accepted_at"]  # 초 포함 시각
                if text:
                    result.hard_risk = check_hard_risk(text)
                    if result.hard_risk:
                        result.notes.append(
                            f"10-Q/K 본문 리스크문구: {result.hard_risk.risk_type}"
                            f"({result.hard_risk.matched_keyword})")
            except Exception as e:
                result.notes.append(f"10-Q/K 본문 리스크 스캔 실패(무시): {type(e).__name__}")
    else:
        item = fetch_latest_8k(ticker, use_sample=use_sample)
        result = DisclosureResult(item=item, route=route)

    # 2) 8-K Item 라우팅 (8-K만)
    if route["needs_item_router"]:
        item_no = item.meta.get("item_no") or (
            extract_item_numbers(item.body)[:1] or [None])[0]
        if item_no:
            result.routed_item = route_item(item_no)

    # 3) 하드룰 (LLM보다 우선). XBRL 분기에서 본문 스캔으로 이미 잡았으면 유지.
    if result.hard_risk is None:
        result.hard_risk = check_hard_risk(item.body)
    if result.hard_risk:
        result.notes.append(
            f"하드리스크 감지: {result.hard_risk.risk_type} "
            f"→ {result.hard_risk.trade_permission} (LLM 무관 강제)")

    # 4) LLM 분석 (키 있을 때만) — 신호는 원본 보존, 권한 종합은 5단계에서
    if run_llm:
        from app.analyzers.disclosure_analyzer import analyze
        result.signal = analyze(item)
        if result.signal and result.hard_risk:
            result.signal.hard_risk_flag = True   # 표시만
            result.signal.risk_score = max(
                result.signal.risk_score, result.hard_risk.risk_score_min)
    else:
        result.notes.append("run_llm=False → LLM 분석 건너뜀(배선만 검증).")

    # 5) 최종 매매권한 종합 (하드룰 / LLM / Item기본 중 가장 보수적 채택)
    result.final_permission, result.final_reason = decide_final_permission(
        result.hard_risk, result.signal, result.routed_item)

    return result

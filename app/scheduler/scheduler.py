"""
수집 스케줄러 — 유니버스를 주기적으로 순회하며 공시·뉴스를 함께 처리한다.

기존 batch_runner의 한계였던 "수집(문서 다운로드) 후에야 증분 비교"를
**메타레벨 증분**으로 끌어올린다:
  1) peek_recent_filings 로 submissions만 1회 호출해 form별 최신 accession 확인
  2) 이미 처리한 accession이면 → 문서 다운로드·LLM·저장을 전부 건너뜀 (skip)
  3) 새 accession일 때만 코어 파이프라인 실행

순서는 companies.priority (우선순위 큐). 한 종목 실패가 사이클을 멈추지 않는다.
뉴스도 같은 순회에 통합 — 프로세스 내 seen 집합으로 재분석(LLM 재호출)을 막는다.
뉴스 영구 저장(news_signals 테이블)은 다음 단계(항목 3).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from app.collectors.sec_collector import peek_recent_filings
from app.pipeline import run_disclosure_pipeline
from app.scheduler.bundle_snapshot import BundleAccumulator
from app.storage.db import (
    is_filing_processed, mark_filing_processed, save_disclosure)
from app.universe.repository import get_active_tickers, mark_processed

DEFAULT_FORMS: tuple[str, ...] = ("8-K",)

# 수집 주기 (팀 명세 2026-07-06): 공시=1시간, 뉴스=5분(이벤트가 잦음).
# 뉴스가 12배 촘촘하므로 틱은 뉴스 주기로 돌리고 공시는 그 배수마다 처리한다.
DISCLOSURE_INTERVAL_SEC = 3600   # 공시 1시간
NEWS_INTERVAL_SEC = 300          # 뉴스 5분


@dataclass
class FilingOutcome:
    ticker: str
    form: str
    accession: str | None
    status: str              # new | unchanged | no-filing | error:<Type>
    result: Any = None       # DisclosureResult | None


@dataclass
class NewsOutcome:
    ticker: str
    passed: int = 0
    dropped: int = 0
    fresh: int = 0           # 이번에 새로 분석한 뉴스 수
    saved: int = 0           # DB에 새로 저장된 수
    total: int = 0
    error: str | None = None


@dataclass
class CycleReport:
    started_at: str
    filings: list[FilingOutcome] = field(default_factory=list)
    news: list[NewsOutcome] = field(default_factory=list)

    @property
    def new(self) -> int:
        return sum(1 for f in self.filings if f.status == "new")

    @property
    def unchanged(self) -> int:
        return sum(1 for f in self.filings if f.status == "unchanged")

    @property
    def errors(self) -> int:
        return sum(1 for f in self.filings if f.status.startswith("error"))


def _process_filing(ticker: str, form: str, meta: dict,
                    run_llm: bool, save: bool) -> FilingOutcome:
    """단일 (종목, form) 최신 제출을 증분 판정 후 필요 시에만 처리."""
    acc = meta.get("accession")
    # 메타레벨 증분: 문서 다운로드 전에 accession만으로 skip 판단
    if is_filing_processed(acc):
        return FilingOutcome(ticker, form, acc, "unchanged")
    try:
        result = run_disclosure_pipeline(
            ticker, form_type=form, use_sample=False, run_llm=run_llm)
        if save:
            save_disclosure(result)
            mark_filing_processed(acc, ticker, form)
            mark_processed(ticker, acc,
                           datetime.now(timezone.utc).isoformat(timespec="seconds"))
        return FilingOutcome(ticker, form, acc, "new", result)
    except Exception as e:  # 한 건 실패가 사이클을 멈추지 않게
        return FilingOutcome(ticker, form, acc, f"error:{type(e).__name__}")


def _process_news(ticker: str, limit: int, run_llm: bool, save: bool,
                  seen: set[str], acc: BundleAccumulator | None = None) -> NewsOutcome:
    """종목 뉴스 수집 + 사전필터(+LLM) + 저장.

    dedup 2단: 사이클 내 seen 집합 + (save 시) DB news_signals 조회로
    스케줄러 재시작에도 재분석/재LLM을 막는다. 키는 google_link(기사별 유니크).

    acc가 있으면 분석한 기사 결과를 번들 누적기에 종목별로 쌓는다(오늘 전체 집계용).
    이미 seen인 기사는 이번 순회에서 재분석하지 않으므로, 누적기에는 그 기사를
    처음 분석했던 사이클에 담긴다(장기 실행 시 오늘분이 점진적으로 채워짐).
    """
    from app.collectors.news_collector import fetch_latest_news
    from app.news_pipeline import run_news_pipeline
    from app.storage.db import is_news_seen, news_dedup_key, save_news

    out = NewsOutcome(ticker=ticker)
    try:
        items = fetch_latest_news(ticker, limit=limit)
    except Exception as e:
        out.error = f"{type(e).__name__}"
        return out

    out.total = len(items)
    for it in items:
        key = news_dedup_key(it)
        if key in seen:                      # 사이클 내 중복
            continue
        seen.add(key)
        if save and is_news_seen(key):       # 이전 실행에서 이미 저장 → skip
            continue
        out.fresh += 1
        r = run_news_pipeline(it, run_llm=run_llm)
        if acc is not None:                  # 오늘 뉴스 전체 집계용 누적
            acc.add_news(ticker, key, r)
        if r.dropped:
            out.dropped += 1
        else:
            out.passed += 1
        if save and save_news(r) is not None:
            out.saved += 1
    return out


def _save_ticker_bundles(ticker: str, trade_date: str, acc: BundleAccumulator,
                         do_disclosure: bool, do_news: bool) -> None:
    """누적기의 오늘 결과로 종목당 집계 번들을 만들어 tb_disclosure/tb_news에 append.

    do_disclosure/do_news는 이중 주기 반영 — 공시 틱에만 tb_disclosure,
    뉴스 틱마다 tb_news 행을 남긴다. 신호가 없어도(build가 has_signal=0 빈 행)
    항상 행을 생성해 사이클당 종목 수만큼 균일하게 쌓는다.
    """
    from app.common.analysis_bundle import (build_disclosure_bundle,
                                            build_news_bundle)
    from app.storage.db import save_disclosure_bundle, save_news_bundle

    if do_disclosure:
        # 방향성·원문 메타는 대표 공시 1건에서, 위험·차단은 오늘 전체를 필드별 집계
        # (명세 §05: "한 행으로 모으되 hard_block=1·risk_score 최댓값 보존").
        bundle = build_disclosure_bundle(
            ticker, trade_date, disclosure_result=acc.disclosure_rep(ticker))
        risk_max = acc.disclosure_risk_max(ticker)
        if risk_max > bundle.risk_score:
            bundle.risk_score = risk_max            # 최고 위험 보존(집계에 안 묻히게)
        blocked, reason = acc.disclosure_block(ticker)
        if blocked and not bundle.hard_block:
            bundle.hard_block = 1                    # 하나라도 파산·상폐면 차단
            bundle.hard_block_reason = bundle.hard_block_reason or reason
        save_disclosure_bundle(bundle)
    if do_news:
        nb = build_news_bundle(ticker, trade_date, news_results=acc.news_for(ticker))
        if nb.has_signal:                        # 대표 event_type ↔ 오늘 공시 filing_no 매칭
            nb.disclosure_ref = acc.disclosure_ref_for(ticker, nb.event_type)
        save_news_bundle(nb)


def run_cycle(limit: int = 5, forms: tuple[str, ...] = DEFAULT_FORMS,
              run_news: bool = False, news_limit: int = 6,
              run_llm: bool = False, save: bool = False,
              seen_news: set[str] | None = None,
              process_filings: bool = True,
              save_bundles: bool = False,
              bundle_acc: BundleAccumulator | None = None,
              polite_delay: float = 0.15) -> CycleReport:
    """유니버스 1회 순회. 우선순위 순으로 종목별 공시(+뉴스) 처리.

    process_filings=False면 공시는 건너뛰고 뉴스만 처리한다(뉴스 주기가 공시보다
    촘촘한 이중 주기에서, 공시 차례가 아닌 틱에 쓰인다).

    save_bundles=True면 종목당 집계 번들을 tb_disclosure/tb_news에 append한다
    (팀 명세 §05·§06: 매 사이클 종목마다 1행, 신호 없으면 has_signal=0 빈 행).
    per-signal 저장(save)과 독립 — save 없이도 번들 스냅샷만 남길 수 있다.
    bundle_acc를 주면 여러 사이클에 걸쳐 오늘분을 누적(run_forever), 없으면 이 한
    사이클 범위로 새로 만든다(run_cycle 단독/--once).
    """
    seen_news = seen_news if seen_news is not None else set()
    trade_date = date.today().isoformat()
    if save_bundles:
        if bundle_acc is None:
            bundle_acc = BundleAccumulator(trade_date=trade_date)
        bundle_acc.roll(trade_date)          # 거래일 바뀌면 누적 초기화
    report = CycleReport(
        started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    for ticker in get_active_tickers(limit):
        # --- 공시: submissions 1회로 form별 최신 메타를 엿본 뒤 증분 처리 ---
        if process_filings:
            try:
                metas = peek_recent_filings(ticker, forms)
            except Exception as e:
                for form in forms:
                    report.filings.append(
                        FilingOutcome(ticker, form, None, f"error:{type(e).__name__}"))
                metas = {}
            for form in forms:
                meta = metas.get(form)
                if not meta:
                    report.filings.append(
                        FilingOutcome(ticker, form, None, "no-filing"))
                    continue
                outcome = _process_filing(ticker, form, meta, run_llm, save)
                report.filings.append(outcome)
                if save_bundles and outcome.status == "new":
                    bundle_acc.add_disclosure(ticker, outcome.accession, outcome.result)

        # --- 뉴스: 같은 순회에 통합 ---
        if run_news:
            report.news.append(_process_news(
                ticker, news_limit, run_llm, save, seen_news,
                acc=bundle_acc if save_bundles else None))

        # --- 번들 스냅샷: 종목당 집계 1행 append (공시 틱=tb_disclosure, 뉴스=tb_news) ---
        if save_bundles:
            _save_ticker_bundles(ticker, trade_date, bundle_acc,
                                 do_disclosure=process_filings, do_news=run_news)

        time.sleep(polite_delay)  # SEC/RSS 예의 (rate limit)

    return report


def run_forever(disclosure_interval_sec: int = DISCLOSURE_INTERVAL_SEC,
                news_interval_sec: int = NEWS_INTERVAL_SEC,
                **cycle_kwargs) -> None:
    """이중 주기로 run_cycle을 반복. Ctrl+C로 종료.

    틱은 더 촘촘한 뉴스 주기로 돌고(뉴스는 매 틱 처리), 공시는 disclosure 주기가
    지났을 때만 처리한다. 예) 공시 3600s·뉴스 300s → 뉴스 12틱마다 공시 1회.
    뉴스를 안 돌리면(run_news=False) 틱=공시 주기라 매 틱 공시만 처리한다.
    seen_news 집합을 틱 간 공유해 같은 뉴스의 반복 LLM 호출을 막는다.
    """
    seen_news: set[str] = set()
    # 번들 누적기는 프로세스 수명 동안 유지 — 오늘분 공시·뉴스가 사이클 간 누적된다.
    bundle_acc = (BundleAccumulator(trade_date=date.today().isoformat())
                  if cycle_kwargs.get("save_bundles") else None)
    cycle = 0
    run_news = cycle_kwargs.get("run_news", False)
    tick = news_interval_sec if run_news else disclosure_interval_sec
    last_disclosure: float | None = None   # None → 첫 틱에 공시 실행
    try:
        while True:
            cycle += 1
            now = time.monotonic()
            do_filings = (last_disclosure is None
                          or now - last_disclosure >= disclosure_interval_sec)
            if do_filings:
                last_disclosure = now
            report = run_cycle(seen_news=seen_news, bundle_acc=bundle_acc,
                               process_filings=do_filings, **cycle_kwargs)
            yield_summary(cycle, report, did_filings=do_filings)
            time.sleep(tick)
    except KeyboardInterrupt:
        print("\n⏹️  스케줄러 종료 (Ctrl+C)")


def yield_summary(cycle: int, report: CycleReport,
                  did_filings: bool = True) -> None:
    """사이클 요약 한 줄 출력 (엔트리포인트가 상세는 별도 렌더)."""
    n = len(report.filings)
    disc_note = (f"공시 {n}건 (new {report.new}·unchanged {report.unchanged}"
                 f"·err {report.errors})" if did_filings
                 else "공시 skip(주기 대기)")
    news_note = ""
    if report.news:
        fresh = sum(x.fresh for x in report.news)
        passed = sum(x.passed for x in report.news)
        saved = sum(x.saved for x in report.news)
        news_note = f" | 뉴스 fresh {fresh}·통과 {passed}·저장 {saved}"
    print(f"[cycle {cycle} @ {report.started_at}] {disc_note}{news_note}")

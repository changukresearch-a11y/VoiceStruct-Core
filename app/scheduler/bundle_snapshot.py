"""
번들 스냅샷 누적기 — 매 사이클 50종목 각각 tb_disclosure/tb_news에 1행씩 append.

팀 명세(2026-07-08) §05·§06: 공시·뉴스를 종목당 사이클당 **집계 1행**으로
tb_disclosure/tb_news에 시계열 append(덮어쓰기 X). 신호 없는 종목도 has_signal=0
행을 남겨 **항상 50행/사이클로 균일**. Strategist는 종목별 최신 행을 읽는다.

per-signal 로그(disclosure_signals/news_signals)와 **별개** — 저 테이블은 백테스트·
증분용, tb_*는 전략가 출력 전용. 이 누적기는 스케줄러의 한 수집 순회 결과를 모아
종목당 하나의 번들로 집계해 저장한다(수집을 이중으로 하지 않는다).

증분과의 조화가 핵심 — 스케줄러는 새 공시/기사만 LLM 분석하지만, 번들은 매 사이클
'오늘까지 분석된 전체'를 집계해야 한다. 그래서 누적기가 오늘 분석 결과를 종목별로
프로세스 메모리에 쌓아두고, 매 사이클 그 전체로 번들을 만든다.
  - 공시: 오늘 여러 건을 **한 행으로 집계**하되(명세 §05) 방향성(event_type·sentiment·
    importance)은 대표 1건(파산·상폐 hard_block 우선 → importance 최대)에서 뽑고,
    **hard_block=OR·risk_score=최댓값으로 보존**(치명 위험이 집계에 묻히지 않게).
  - 뉴스: 오늘 분석한 기사를 news_key로 누적(중복제거) → build_news_bundle이 전체를
    신뢰가중으로 필드별 집계(대표 헤드라인·점수).

한계(문서화): 누적이 프로세스 메모리라 재시작 시 초기화 → 재시작 전 분석분은 새
신호가 뜨기 전까지 번들에서 빠질 수 있다(기존 스케줄러 seen-집합 dedup과 같은 성격).
steady-state는 장기 실행(run_forever)에서 채워진다. 완전 복원은 후속(재시작 시
disclosure_signals/news_signals에서 오늘분 로드).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.common.analysis_bundle import _n10  # 0~10→0~1 정규화 재사용(집계 척도 일관)
from app.common.ontology import norm_event   # 공시/뉴스 event_type 정규화(매칭 일관)

_BLOCK = {"BLOCK_ALL", "BLOCK_BUY"}


def _importance(result: Any) -> float:
    sig = getattr(result, "signal", None)
    return float(getattr(sig, "importance", 0) or 0) if sig is not None else -1.0


def _is_block(result: Any) -> bool:
    return getattr(result, "final_permission", None) in _BLOCK


@dataclass
class BundleAccumulator:
    """오늘 분석된 공시·뉴스 결과를 종목별로 누적 → 매 사이클 집계 번들 산출.

    같은 trade_date 안에서만 유효. 날짜가 바뀌면 roll()로 초기화한다.
    공시·뉴스 모두 {키: 결과} 맵으로 저장(키 중복 시 갱신 → 재feed에도 중복 없음).
    """
    trade_date: str
    _disc: dict[str, dict[str, Any]] = field(default_factory=dict)  # ticker -> {accession: DisclosureResult}
    _news: dict[str, dict[str, Any]] = field(default_factory=dict)  # ticker -> {news_key: NewsResult}

    def roll(self, trade_date: str) -> None:
        """거래일이 바뀌면 누적을 비운다(어제 신호가 오늘로 새지 않게)."""
        if trade_date != self.trade_date:
            self.trade_date = trade_date
            self._disc.clear()
            self._news.clear()

    # ── 공시 ──────────────────────────────────────────────
    def add_disclosure(self, ticker: str, key: str | None, result: Any) -> None:
        """오늘 공시 1건을 누적. key=accession(고유). result=None(무공시)이면 무시."""
        if result is None:
            return
        bucket = self._disc.setdefault(ticker, {})
        bucket[key or f"_{len(bucket)}"] = result

    def _disc_results(self, ticker: str) -> list[Any]:
        return list(self._disc.get(ticker, {}).values())

    def disclosure_rep(self, ticker: str) -> Any:
        """방향성·원문 메타의 대표 1건 — 파산·상폐(hard_block) 우선 → importance 최대.
        (집계에 묻히면 안 되는 치명 이벤트를 행의 얼굴로.) 없으면 None."""
        results = self._disc_results(ticker)
        if not results:
            return None
        blocks = [r for r in results if _is_block(r)]
        return max(blocks or results, key=_importance)

    def disclosure_risk_max(self, ticker: str) -> float:
        """오늘 공시 전체의 risk_score 최댓값(0~1). 대표가 아니어도 최고 위험 보존."""
        risks = [_n10(getattr(r.signal, "risk_score", 0))
                 for r in self._disc_results(ticker)
                 if getattr(r, "signal", None) is not None]
        return max(risks) if risks else 0.0

    def disclosure_block(self, ticker: str) -> tuple[bool, str | None]:
        """오늘 공시 중 하나라도 hard_block이면 (True, 사유). OR 집계."""
        for r in self._disc_results(ticker):
            if _is_block(r):
                return True, getattr(r, "final_reason", None)
        return False, None

    def disclosure_ref_for(self, ticker: str, event_type: str | None) -> str | None:
        """뉴스 대표 event_type을 뒷받침하는 오늘 공시의 filing_no(accession). 없으면 None.

        명세 최최종(2026-07-09) 뉴스 #10 disclosure_ref — 삭제한 루머/팩트 이진판별 대신
        **공식 문서 존재 여부**로 사실성 보강. 매칭은 event_type 일치(같은 종목·오늘 범위),
        여럿이면 importance 최대 1건. event_type 없음/'other'는 광범위 오매칭 방지로 제외.

        한계(bundle_snapshot 누적과 동일): _disc는 프로세스 메모리라 재시작 직후엔 오늘
        공시가 비어 매칭이 잠깐 빌 수 있다. 다음 공시 틱 이후 최신 행에 채워진다.
        """
        if not event_type or event_type == "other":
            return None
        best_imp, best_acc = -1.0, None
        for r in self._disc_results(ticker):
            sig = getattr(r, "signal", None)
            if sig is None:
                continue
            if norm_event(getattr(sig, "event_type", None)) != event_type:
                continue
            acc = (getattr(r.item, "meta", {}) or {}).get("accession_no")
            if not acc:
                continue
            imp = float(getattr(sig, "importance", 0) or 0)
            if imp > best_imp:
                best_imp, best_acc = imp, acc
        return best_acc

    # ── 뉴스 ──────────────────────────────────────────────
    def add_news(self, ticker: str, key: str, result: Any) -> None:
        """오늘 분석(또는 사전필터drop)한 기사 1건을 누적. 같은 key면 갱신(중복 방지)."""
        self._news.setdefault(ticker, {})[key] = result

    def news_for(self, ticker: str) -> list[Any]:
        """종목의 오늘 뉴스 결과 전체(없으면 [] → build가 has_signal=0 빈 행)."""
        return list(self._news.get(ticker, {}).values())

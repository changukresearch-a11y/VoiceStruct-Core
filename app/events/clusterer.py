"""
뉴스 화제성(Buzz) 클러스터링 — LLM 없이 코드로만.

같은 종목 뉴스들 안에서 '같은 이벤트'를 다룬 기사를 묶는다.
로이터·블룸버그·CNBC가 같은 M&A를 각자 쓰면 → 1개 이벤트(출처 3).
'얼마나 시끄러운가(buzz)'와 '믿을 출처가 교차확인했나(cross_source)'를
분리해 낸다. (화제성 ≠ 신뢰: 소셜 화제 폭발은 오히려 펌프 위험이라
buzz는 전체를, cross_source는 ALLOW급만 센다.)

파라미터(사용자 확정 2026-07-02):
  - 제목 토큰 Jaccard 유사도 ≥ 0.35 → 같은 이벤트
    (0.5는 정규화 후에도 실적처럼 표현 다른 같은 이벤트를 놓쳐 0.35로 하향)
  - published_at 72h 이내 → 같은 이벤트
  - cross_source_confirmed = 서로 다른 ALLOW 출처 2곳 이상
  - 토큰 정규화: 숫자·금액단위 제거 + 복수/3인칭 -s 통일
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

_SIM_THRESHOLD = 0.35     # 제목 토큰 Jaccard 유사도 임계값
_TIME_WINDOW_H = 72       # 같은 이벤트로 볼 시간창(시간)
_CROSS_MIN_ALLOW = 2      # cross_source_confirmed: 서로 다른 ALLOW 출처 최소 수

# 불용어 — 제목 유사도 왜곡을 줄인다. 종목이 같으니 티커/'stock' 등은 노이즈.
# 금액 단위어(billion 등)도 표기가 흔들려($40B/40 billion) 제거한다.
_STOP = {
    "the", "a", "an", "to", "of", "in", "on", "for", "and", "or", "is", "are",
    "as", "at", "by", "with", "from", "its", "it", "be", "will", "after",
    "stock", "stocks", "shares", "share", "inc", "corp", "co", "says", "say",
    "reportedly", "amid", "new", "up", "down", "vs", "this", "that", "than",
    "billion", "bn", "million", "trillion", "usd", "dollar", "dollars",
}
_WORD = re.compile(r"[a-z0-9]+")


def _stem(w: str) -> str:
    """가벼운 복수/3인칭 -s 정규화 (acquires→acquire, holdings→holding)."""
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _tokens(title: str) -> set[str]:
    out: set[str] = set()
    for w in _WORD.findall(title.lower()):
        if w in _STOP or len(w) <= 1:
            continue
        if w[0].isdigit():          # 숫자·금액 토큰 제거 ($40B, 40, 40bn)
            continue
        out.add(_stem(w))
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _within_window(t1: Any, t2: Any) -> bool:
    if t1 is None or t2 is None:
        return True   # 시간 정보 없으면 제목 유사도만으로 판단
    return abs(t1 - t2) <= timedelta(hours=_TIME_WINDOW_H)


def _source_of(result: Any) -> str:
    item = result.item
    meta = getattr(item, "meta", {}) or {}
    return (meta.get("source") or item.url or "").strip().lower()


@dataclass
class Cluster:
    """같은 이벤트를 다룬 뉴스 묶음."""
    members: list[Any] = field(default_factory=list)   # NewsResult 리스트

    @property
    def buzz(self) -> int:
        """이 이벤트를 다룬 기사 수 (얼마나 시끄러운가)."""
        return len(self.members)

    @property
    def sources(self) -> set[str]:
        return {s for r in self.members if (s := _source_of(r))}

    @property
    def allow_sources(self) -> set[str]:
        """ALLOW 등급 출처만 (신뢰 교차확인용)."""
        return {s for r in self.members
                if getattr(r, "source_grade", None) == "ALLOW"
                and (s := _source_of(r))}

    @property
    def cross_source_confirmed(self) -> bool:
        """서로 다른 ALLOW 출처 2곳 이상이 같은 이벤트를 다뤘나."""
        return len(self.allow_sources) >= _CROSS_MIN_ALLOW

    def representative(self) -> Any:
        """대표 기사 = 신호 있는 것 우선, importance 최고."""
        with_sig = [r for r in self.members if getattr(r, "signal", None)]
        pool = with_sig or self.members
        return max(pool, key=lambda r: getattr(
            getattr(r, "signal", None), "importance", 0) or 0)


def cluster_news(results: list, sim: float = _SIM_THRESHOLD) -> list[Cluster]:
    """뉴스(NewsResult)들을 같은 이벤트끼리 greedy 묶기.

    seed 기사 기준 단일 패스 — MVP엔 충분(정밀 병합은 Phase2).
    입력은 dropped 아닌(사전필터 통과) 뉴스를 넣는다.
    """
    toks = [(_tokens(r.item.title or ""), r) for r in results]
    clusters: list[Cluster] = []
    assigned = [False] * len(toks)

    for i, (ti, ri) in enumerate(toks):
        if assigned[i]:
            continue
        c = Cluster(members=[ri])
        assigned[i] = True
        for j in range(i + 1, len(toks)):
            if assigned[j]:
                continue
            tj, rj = toks[j]
            if (_jaccard(ti, tj) >= sim
                    and _within_window(ri.item.published_at,
                                       rj.item.published_at)):
                c.members.append(rj)
                assigned[j] = True
        clusters.append(c)
    return clusters


def summarize_buzz(clusters: list[Cluster]) -> dict:
    """번들에 실을 화제성 집계값."""
    return {
        "event_count": len(clusters),
        "top_buzz": max((c.buzz for c in clusters), default=0),
        "cross_source_confirmed": any(c.cross_source_confirmed for c in clusters),
    }

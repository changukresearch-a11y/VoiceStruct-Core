"""
성과 리포트 — 채워진 전방수익률을 이벤트/센티먼트/출처별로 집계한다.

"정보가 실제로 주가에 먹혔나"를 측정해 어떤 이벤트타입·출처가 성과가 좋은지
사람이 보고 판단하기 위한 것. **가중치는 여기서 자동으로 바꾸지 않는다**
(표본 부족 시 과적합 — 메모리 MVP 컷라인: 수동 기록·분석부터).
"""
from __future__ import annotations

from app.storage.db import filled_returns


def _agg(rows: list, key: str) -> list[dict]:
    """key(컬럼)별로 건수·평균수익률·적중률 집계."""
    buckets: dict[str, dict] = {}
    for r in rows:
        k = r[key] if key in r.keys() else None
        k = k if k is not None else "(none)"
        b = buckets.setdefault(k, {"n": 0, "s1": 0.0, "s3": 0.0, "s5": 0.0,
                                   "hit": 0, "judged": 0})
        b["n"] += 1
        b["s1"] += r["return_1d"] or 0.0
        b["s3"] += r["return_3d"] or 0.0
        b["s5"] += r["return_5d"] or 0.0
        if r["outcome"] in ("hit", "miss"):
            b["judged"] += 1
            b["hit"] += 1 if r["outcome"] == "hit" else 0
    out = []
    for k, b in buckets.items():
        n = b["n"]
        out.append({
            "key": k, "n": n,
            "avg_1d": round(b["s1"] / n, 2),
            "avg_3d": round(b["s3"] / n, 2),
            "avg_5d": round(b["s5"] / n, 2),
            "hit_rate": (round(100 * b["hit"] / b["judged"], 1)
                         if b["judged"] else None),
        })
    return sorted(out, key=lambda x: -x["n"])


def _fmt_table(title: str, rows: list[dict]) -> str:
    if not rows:
        return f"  {title}: (데이터 없음)\n"
    lines = [f"  {title}",
             f"    {'key':16} {'n':>4} {'avg1d':>7} {'avg3d':>7} {'avg5d':>7} {'적중률':>7}"]
    for r in rows:
        hr = f"{r['hit_rate']}%" if r["hit_rate"] is not None else "-"
        lines.append(f"    {str(r['key'])[:16]:16} {r['n']:>4} "
                     f"{r['avg_1d']:>7} {r['avg_3d']:>7} {r['avg_5d']:>7} {hr:>7}")
    return "\n".join(lines) + "\n"


def performance_report() -> str:
    """공시·뉴스 성과 리포트 문자열."""
    out = ["📈 백테스트 성과 리포트 (수익률 %, 적중률=센티먼트 방향 일치)\n"]

    disc = filled_returns("disclosure_signals")
    out.append(f"── 공시 (표본 {len(disc)}) ──")
    out.append(_fmt_table("event_type별", _agg(disc, "event_type")))
    out.append(_fmt_table("sentiment별", _agg(disc, "sentiment")))

    news = filled_returns("news_signals")
    out.append(f"── 뉴스 (표본 {len(news)}) ──")
    out.append(_fmt_table("event_type별", _agg(news, "event_type")))
    out.append(_fmt_table("source_grade별", _agg(news, "source_grade")))

    if not disc and not news:
        out.append("\n(아직 수익률이 채워진 신호가 없음 — 신호가 5거래일 이상 "
                   "지난 뒤 `--fill` 실행)")
    return "\n".join(out)

"""원문 근거 매핑 (CAREBASE_DESIGN §4, DB명세 9장).

구조화 필드값 → 그 값이 나온 segment(시간 구간)에 연결. 순수 함수.
"""

from app.domains.carebase.schema import EMOTION_EVIDENCE_TRIGGER


def _first_segment_containing(segments: list[dict], needle: str) -> dict | None:
    return next((s for s in segments if needle in s.get("text", "")), None)


def _first_segment_by_needle_priority(segments: list[dict], needles: list[str]) -> dict | None:
    """needle을 우선순위 순서로 훑어 매칭. 앞 needle이 더 구체적(정확한 근거)."""
    for needle in needles:
        seg = _first_segment_containing(segments, needle)
        if seg:
            return seg
    return None


def _emit(evidences: list[dict], field_name: str, field_value: str, seg: dict) -> None:
    evidences.append(
        {
            "field_name": field_name,
            "field_value": field_value,
            "evidence_text": seg.get("text", ""),
            "start_time": seg.get("start_time"),
            "end_time": seg.get("end_time"),
            "speaker": seg.get("speaker"),
            "confidence": seg.get("confidence"),
        }
    )


def map(draft: dict, segments: list[dict]) -> list[dict]:
    evidences: list[dict] = []

    # people / places: 값 문자열이 포함된 첫 segment
    for field in ("people", "places"):
        for value in draft.get(field, []):
            seg = _first_segment_containing(segments, value)
            if seg:
                _emit(evidences, field, value, seg)

    # time_reference: 어제/오늘/헷갈리네요 중 하나 포함 (DB명세 9.2)
    tr = draft.get("time_reference")
    if tr:
        # 혼동 표현(헷갈리네요) 구간을 우선 근거로 (단순 "오늘" 언급보다 구체적)
        seg = _first_segment_by_needle_priority(segments, ["헷갈리네요", "어제", "오늘"])
        if seg:
            _emit(evidences, "time_reference", tr, seg)

    # emotion: 라벨 → 트리거 어간 포함 segment
    for emo in draft.get("emotion", []):
        trigger = EMOTION_EVIDENCE_TRIGGER.get(emo)
        if trigger:
            seg = _first_segment_containing(segments, trigger)
            if seg:
                _emit(evidences, "emotion", emo, seg)

    # risk: candidate.evidence_text 포함 segment 우선
    for cand in draft.get("risk_signal_candidates", []):
        seg = _first_segment_containing(segments, cand["evidence_text"]) or (
            _first_segment_by_needle_priority(segments, ["어제였나", "오늘이었나"])
        )
        if seg:
            _emit(evidences, "risk_signal_candidates", cand["category"], seg)

    return evidences

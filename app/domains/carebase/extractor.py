"""규칙 기반 CareBase 구조화 (CAREBASE_DESIGN §2, DECISIONS D-05).

순수 함수: (cleaned_transcript, segments) -> dict. DB·시간·랜덤 의존 없음.
NOTE(Phase2): LLM 추출(llm_extractor)로 교체, 이 규칙 로직은 fallback으로 유지.
"""

from app.domains.carebase import schema as S


def _find_segment_text(segments: list[dict], phrase: str) -> str | None:
    for seg in segments:
        if phrase in seg.get("text", ""):
            return seg["text"]
    return None


def _summarize(text: str, people: list[str], places: list[str]) -> str:
    who = "와 ".join(people) if people else "사용자"
    where = places[0] if places else None
    if where:
        return f"사용자는 {who}와 {where}에 다녀온 일을 회상했다."
    return "사용자가 지난 일을 회상했다."


def _topic(people: list[str], places: list[str]) -> str:
    if people and places:
        return f"가족과 {places[0]} 방문"
    if places:
        return f"{places[0]} 관련 기억"
    return "일상 기억"


def _missing(
    people: list[str],
    places: list[str],
    time_reference: str | None,
    emotion: list[str],
    summary: str,
) -> list[str]:
    filled = {
        "memory_summary": bool(summary),
        "people": bool(people),
        "places": bool(places),
        "time_reference": bool(time_reference),
        "emotion": bool(emotion),
    }
    return [k for k in S.REQUIRED_FIELDS if not filled[k]]


def extract(cleaned_transcript: str, segments: list[dict]) -> dict:
    raw = " ".join(s.get("text", "") for s in segments)
    haystack = cleaned_transcript + " " + raw

    people = [w for w in S.PEOPLE_LEXICON if w in haystack]
    places = [w for w in S.PLACES_LEXICON if w in haystack]

    emotion: list[str] = []
    for trigger, label in S.EMOTION_RULES:
        if trigger in haystack and label not in emotion:
            emotion.append(label)

    time_reference: str | None = None
    if any(p in haystack for p in S.TIME_CONFUSION_PHRASES):
        time_reference = "오늘 또는 어제"
    elif "오늘" in haystack:
        time_reference = "오늘"

    risks: list[dict] = []
    for phrase in S.TIME_CONFUSION_PHRASES:
        if phrase in haystack:
            risks.append(
                {
                    "category": "TIME_CONFUSION",
                    "evidence_text": _find_segment_text(segments, phrase) or phrase,
                    "strength": 1,
                    "notice": "진단이 아니라 사용자 자기기록 기반 참고 신호입니다.",
                }
            )
            break  # MVP: 최초 1건만

    summary = _summarize(cleaned_transcript, people, places)

    return {
        "domain": S.DOMAIN,
        "schema_version": S.SCHEMA_VERSION,
        "memory_summary": summary,
        "people": people,
        "places": places,
        "time_reference": time_reference,
        "emotion": emotion,
        "topic": _topic(people, places),
        "memory_type": "daily_memory",
        "risk_signal_candidates": risks,
        "missing_fields": _missing(people, places, time_reference, emotion, summary),
        "requires_user_confirmation": True,
        "safety_notice": S.SAFETY_NOTICE,
    }

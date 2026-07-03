# CareBase Memory 도메인 로직 상세 설계 (S3 심장부)

> 대상 파일: `app/domains/carebase/{schema,extractor,safety_rules,evidence_mapper}.py`
> 기준: DB-API 명세서 8~10장, DECISIONS.md (D-05 규칙기반, D-09)
> 목적: 구조화 실행(`POST /api/structure/run`)의 내부 로직을 구현 직전 수준으로 확정

---

## 0. 전체 흐름 (structure_service 관점)

```
run(transcript_id, domain):
  1. domain 검증           → INVALID_DOMAIN (400)
  2. transcript 조회        → TRANSCRIPT_NOT_FOUND (404)
  3. cleaned_transcript, segments = load(transcript)
  4. draft = extractor.extract(cleaned_transcript, segments)   # ← §2
  5. draft = safety_rules.apply(draft)                          # ← §3
  6. structured_id = id_utils.new("structured")
  7. save StructuredRecord(ai_structured_json=draft, status=AI_TEMP)
  8. evidences = evidence_mapper.map(draft, segments)           # ← §4
  9. save EvidenceRecord[] (evidences)
 10. audio.status = STRUCTURED
 11. return draft, evidence_count=len(evidences)
```

**설계 원칙**
- extractor는 **순수 함수**(입력 텍스트/세그먼트 → dict). DB·시간·랜덤 의존 없음 → 테스트 쉬움.
- safety_rules는 **dict in → dict out** 순수 변환.
- evidence_mapper는 **(draft, segments) → list[dict]** 순수 함수.
- 부작용(DB저장·ID생성·상태전이)은 전부 service 계층에서. 도메인 모듈은 계산만.

---

## 1. schema.py — 구조화 스키마 정의

출력 필드(지시서 10.3 / DB명세 7.4):

```python
# app/domains/carebase/schema.py
from dataclasses import dataclass, field

DOMAIN = "carebase_memory"
SCHEMA_VERSION = "carebase_memory_v1"
SAFETY_NOTICE = "이 결과는 진단이 아니라 사용자 자기기록 기반 참고 신호입니다."

# 필수에 가까운 필드 (missing_fields 판정 대상) — DB명세 8.3
REQUIRED_FIELDS = ["memory_summary", "people", "places", "time_reference", "emotion"]

# evidence 생성 대상 필드 — DB명세 3.4 / 9장
EVIDENCE_FIELDS = ["people", "places", "time_reference", "emotion", "risk_signal_candidates"]
```

> Pydantic 응답 모델(`CareBaseStructuredJson`)은 `app/schemas/structure_schema.py`(DB명세 7.4)에 이미 정의됨. schema.py는 **상수/사전(dictionary) + 규칙 테이블**을 담당.

---

## 2. extractor.py — 규칙 기반 추출

### 2.1 규칙 사전 (DB명세 8.2)

```python
PEOPLE_LEXICON = ["아버지", "어머니", "할머니", "할아버지", "가족", "친구"]
PLACES_LEXICON = ["병원", "집", "학교", "회사", "공원", "시장", "교회"]

# 감정: 트리거 표현 → 라벨
EMOTION_RULES = [
    ("마음이 놓였", "안도"),
    ("걱정", "걱정"),
    ("기뻤", "기쁨"),
    ("슬펐", "슬픔"),
    ("무서웠", "불안"),
]

# 시간 혼동 표현 (time_reference + risk 둘 다 트리거)
TIME_CONFUSION_PHRASES = ["어제였나 오늘이었나", "오늘인지 어제인지", "언제였는지"]
```

> **주의**: DB명세 원문 "마음이 놓였습니다" 전체가 아니라 어간 "마음이 놓였"로 매칭해야 "놓였습니다/놓였어요" 변형을 잡음. (evidence 매핑은 별개 — §4.4)

### 2.2 필드별 추출 로직 (의사코드)

```python
def extract(cleaned_transcript: str, segments: list[dict]) -> dict:
    text = cleaned_transcript
    raw = " ".join(s["text"] for s in segments)   # 원문 근거 탐색용
    haystack = text + " " + raw                    # 정리본+원문 둘 다 검사

    people  = [w for w in PEOPLE_LEXICON if w in haystack]
    places  = [w for w in PLACES_LEXICON if w in haystack]

    emotion = []
    for trigger, label in EMOTION_RULES:
        if trigger in haystack and label not in emotion:
            emotion.append(label)

    # time_reference
    time_reference = None
    if any(p in haystack for p in TIME_CONFUSION_PHRASES):
        time_reference = "오늘 또는 어제"
    elif "오늘" in haystack:
        time_reference = "오늘"

    # risk_signal_candidates (MVP = TIME_CONFUSION만)
    risks = []
    for phrase in TIME_CONFUSION_PHRASES:
        if phrase in haystack:
            risks.append({
                "category": "TIME_CONFUSION",
                "evidence_text": _find_segment_text(segments, phrase) or phrase,
                "strength": 1,
                "notice": "진단이 아니라 사용자 자기기록 기반 참고 신호입니다.",
            })
            break   # MVP: 최초 1건만

    draft = {
        "domain": DOMAIN,
        "schema_version": SCHEMA_VERSION,
        "memory_summary": _summarize(text, people, places),   # §2.3
        "people": people,
        "places": places,
        "time_reference": time_reference,
        "emotion": emotion,
        "topic": _topic(people, places),                      # §2.3
        "memory_type": "daily_memory",                        # MVP 고정
        "risk_signal_candidates": risks,
        "missing_fields": _missing(people, places, time_reference, emotion, text),
        "requires_user_confirmation": True,                   # 항상 True (사람 확인 원칙)
        "safety_notice": SAFETY_NOTICE,
    }
    return draft
```

### 2.3 요약/토픽/누락 헬퍼

```python
def _summarize(text, people, places):
    # MVP: 규칙 기반 템플릿. Phase2에서 LLM 교체(D-05).
    who = "와 ".join(people) if people else "사용자"
    where = places[0] if places else None
    if where:
        return f"사용자는 {who}와 {where}에 다녀온 일을 회상했다."
    return "사용자가 지난 일을 회상했다."

def _topic(people, places):
    if people and places:
        return f"가족과 {places[0]} 방문"
    if places:
        return f"{places[0]} 관련 기억"
    return "일상 기억"

def _missing(people, places, time_reference, emotion, summary):
    filled = {
        "memory_summary": bool(summary),
        "people": bool(people),
        "places": bool(places),
        "time_reference": bool(time_reference),
        "emotion": bool(emotion),
    }
    return [k for k in REQUIRED_FIELDS if not filled[k]]
```

### 2.4 Mock 기본 문장 기대값 검증 (DB명세 12.2)

Mock STT 문장:
> "오늘 아버지랑 병원에 갔다 왔는데, 어제였나 오늘이었나 조금 헷갈리네요. 그래도 아버지가 웃으셔서 마음이 놓였습니다."

| 필드 | 기대 결과 | 근거 트리거 |
|------|-----------|-------------|
| people | `["아버지"]` | "아버지" |
| places | `["병원"]` | "병원" |
| time_reference | `"오늘 또는 어제"` | "어제였나 오늘이었나" |
| emotion | `["안도"]` | "마음이 놓였" |
| risk | `[{category:"TIME_CONFUSION", strength:1}]` | "어제였나 오늘이었나" |
| missing_fields | `[]` | 5개 모두 채워짐 |
| requires_user_confirmation | `true` | 고정 |
| topic | `"가족과 병원 방문"` | people+places |

→ **테스트 통과 조건 전부 충족.** ✅

### 2.5 엣지 케이스

| 상황 | 처리 |
|------|------|
| 아무 트리거 없음 | people=[], places=[] ... → `missing_fields`에 다수, `memory_summary`는 기본 템플릿 |
| 감정 여러 개 | 중복 제거하며 순서대로 append |
| 같은 사람 어휘 2회 등장 | `in` 검사라 1회만 추가(리스트에 유일) |
| 시간 혼동 + 단순 "오늘" 동시 | 혼동 우선(`"오늘 또는 어제"`) |
| risk 표현 여러 개 | MVP는 최초 1건만(break). Phase2에서 전량 수집 |

---

## 3. safety_rules.py — 안전 표현 검사/치환

### 3.1 핵심 개념 (DB명세 10장, 지시서 12장)

- **금지 표현**이 부적절한 문맥에 있으면 안전 표현으로 **치환**.
- **허용 문맥**: "진단이 **아니라**", "진단이 **아닌**" 등 부정 문맥은 그대로 둠.
- 처리 대상: 구조화 JSON 전체를 문자열로 훑음. **run + patch 두 시점 모두 적용**(D 문서, DB명세 13.5).

### 3.2 치환 테이블 (DB명세 10.4)

```python
FORBIDDEN_SUBSTITUTIONS = [
    ("치매 의심",     "표현 변화 후보"),
    ("인지저하 판정", "참고 신호 후보"),
    ("인지저하",      "참고 신호 후보"),
    ("질병 진단",     "진단이 아닌 참고 기록"),
    ("위험 등급",     "확인 필요 수준"),
    ("의학적 조언",   "보호자 확인 참고"),
    ("치매",          "표현 변화 후보"),
]

# 이 문맥 안에서는 치환하지 않음 (허용 고지문)
ALLOWED_CONTEXTS = [
    "진단이 아니라",
    "진단이 아닌",
    "진단이 아니라 사용자 자기기록",
]
```

### 3.3 문맥 인식 치환 로직 (의사코드)

```python
def apply(draft: dict) -> dict:
    import json
    text = json.dumps(draft, ensure_ascii=False)

    for forbidden, safe in FORBIDDEN_SUBSTITUTIONS:
        if forbidden not in text:
            continue
        # 허용 문맥 안의 등장은 보존, 그 외만 치환
        text = _replace_except_allowed(text, forbidden, safe)

    result = json.loads(text)
    # safety_notice는 항상 존재 보장 (§3.4)
    result["safety_notice"] = SAFETY_NOTICE
    return result


def _replace_except_allowed(text, forbidden, safe):
    # 허용 문맥에 포함된 forbidden은 자리표시자로 잠깐 보호 → 치환 → 복구
    protected = []
    for i, ctx in enumerate(ALLOWED_CONTEXTS):
        if forbidden in ctx and ctx in text:
            token = f"__SAFE_{i}__"
            text = text.replace(ctx, token)
            protected.append((token, ctx))
    text = text.replace(forbidden, safe)
    for token, ctx in protected:
        text = text.replace(token, ctx)
    return text
```

> **왜 이 방식?** 단순 `str.replace(forbidden, safe)`는 "진단이 아니라..." 고지문 속 "진단"까지 깨뜨림. 허용 문맥을 자리표시자로 보호했다가 되돌리는 방식이 MVP에서 가장 안전하고 단순.

### 3.4 safety_notice 보장

- extractor가 이미 `safety_notice`를 넣지만, safety_rules가 **최종 방어선**으로 다시 강제.
- 모든 CareBase 결과에 고정 문구 존재 → 테스트 `test_safety_rules_no_forbidden_expression` 대비.

### 3.5 테스트 관점 (DB명세 12.1)

```python
def test_safety_rules_no_forbidden_expression():
    draft = {"memory_summary": "치매 의심 소견", "safety_notice": "..."}
    out = safety_rules.apply(draft)
    blob = json.dumps(out, ensure_ascii=False)
    assert "치매 의심" not in blob
    assert "표현 변화 후보" in blob
    # 허용 문맥은 보존
    draft2 = {"safety_notice": "이 결과는 진단이 아니라 사용자 자기기록 기반 참고 신호입니다."}
    out2 = safety_rules.apply(draft2)
    assert "진단이 아니라" in json.dumps(out2, ensure_ascii=False)
```

---

## 4. evidence_mapper.py — 원문 근거 매핑

### 4.1 목적 (DB명세 9장)

구조화 필드값 → 그 값이 **어느 segment(시간 구간)에서 나왔는지** 연결.
대상 필드: `people, places, time_reference, emotion, risk_signal_candidates`.

### 4.2 segment 구조 재확인

```json
{"start_time": 0.0, "end_time": 4.2, "speaker": "speaker_1",
 "text": "오늘 아버지랑 병원에 갔다 왔는데", "confidence": 0.91}
```

### 4.3 매핑 알고리즘 (의사코드)

```python
def map(draft: dict, segments: list[dict]) -> list[dict]:
    evidences = []

    def emit(field_name, field_value, seg):
        evidences.append({
            "field_name": field_name,
            "field_value": field_value,
            "evidence_text": seg["text"],
            "start_time": seg.get("start_time"),
            "end_time": seg.get("end_time"),
            "speaker": seg.get("speaker"),
            "confidence": seg.get("confidence"),
        })

    # people / places: 값 문자열이 포함된 첫 segment
    for field in ("people", "places"):
        for value in draft.get(field, []):
            seg = _first_segment_containing(segments, value)
            if seg:
                emit(field, value, seg)

    # time_reference: needle을 "우선순위 순서"로 매칭 (DB명세 9.2)
    # ⚠️ 구현 시 발견: 세그먼트 바깥 루프로 돌면 첫 세그먼트의 "오늘"에 먼저 걸려
    #    혼동 구간(4.3~) 대신 0.0 구간이 잡힘. needle 우선순위 순서로 훑어야 정확.
    tr = draft.get("time_reference")
    if tr:
        seg = _first_segment_by_needle_priority(segments, ["헷갈리네요", "어제", "오늘"])
        if seg:
            emit("time_reference", tr, seg)

    # emotion: 안도 ← "마음이 놓였" 포함 segment
    for emo in draft.get("emotion", []):
        trigger = EMOTION_EVIDENCE_TRIGGER.get(emo)   # {"안도": "마음이 놓였", ...}
        if trigger:
            seg = _first_segment_containing(segments, trigger)
            if seg:
                emit("emotion", emo, seg)

    # risk: candidate.evidence_text 포함 segment 우선
    for cand in draft.get("risk_signal_candidates", []):
        seg = _first_segment_containing(segments, cand["evidence_text"]) \
              or _first_segment_containing_any(segments, ["어제였나", "오늘이었나"])
        if seg:
            emit("risk_signal_candidates", cand["category"], seg)

    return evidences
```

### 4.4 매핑 트리거 테이블

```python
# emotion 라벨 → 원문에서 찾을 트리거 (extractor의 EMOTION_RULES와 정렬)
EMOTION_EVIDENCE_TRIGGER = {
    "안도": "마음이 놓였",
    "걱정": "걱정",
    "기쁨": "기뻤",
    "슬픔": "슬펐",
    "불안": "무서웠",
}
```

### 4.5 헬퍼

```python
def _first_segment_containing(segments, needle):
    return next((s for s in segments if needle in s["text"]), None)

def _first_segment_containing_any(segments, needles):
    for s in segments:
        if any(n in s["text"] for n in needles):
            return s
    return None
```

### 4.6 Mock 문장 기준 생성되는 Evidence (기대값)

| field_name | field_value | evidence_text(segment) | start~end |
|------------|-------------|------------------------|-----------|
| people | 아버지 | "오늘 아버지랑 병원에 갔다 왔는데" | 0.0~4.2 |
| places | 병원 | "오늘 아버지랑 병원에 갔다 왔는데" | 0.0~4.2 |
| time_reference | 오늘 또는 어제 | "어제였나 오늘이었나 조금 헷갈리네요" | 4.3~8.5 |
| emotion | 안도 | "그래도 아버지가 웃으셔서 마음이 놓였습니다" | 8.6~13.0 |
| risk_signal_candidates | TIME_CONFUSION | "어제였나 오늘이었나 조금 헷갈리네요" | 4.3~8.5 |

→ **총 5건 생성** → 테스트 `count >= 3`, `people/places/time_reference 포함` 충족. ✅

### 4.7 엣지 케이스

| 상황 | 처리 |
|------|------|
| 값은 있는데 어느 segment에도 없음 | evidence 생략(억지 생성 금지) |
| 한 segment에 people+places 동시 | 각각 별도 evidence 2건 생성(같은 시간 구간 공유 OK) |
| segments 비어있음 | evidences=[] 반환, run은 성공하되 evidence_count=0 → 테스트 문장에선 발생 안 함 |
| time_reference=None | 매핑 스킵 |

---

## 5. Phase 2 교체 지점 (미리 표시)

| 모듈 | MVP(지금) | Phase 2 |
|------|-----------|---------|
| extractor | 규칙 사전 매칭 | Claude API 구조화(JSON schema 강제), 규칙은 fallback |
| evidence_mapper | 부분 문자열 포함 매칭 | LLM이 원문 char-span 반환 → segment 시간 매핑, 유사도 기반 |
| safety_rules | 사전 치환 | 분류 모델/LLM 검증 + 사전 치환 이중화 |
| risk 감지 | TIME_CONFUSION 1종 | REPEATED_QUESTION / WORD_FINDING 추가, 세션 간 추적 |

각 파일 상단에 `# NOTE(Phase2): ...` 주석으로 교체 지점 명시.

---

## 6. 구현 체크리스트 (S3용)

- [ ] `schema.py` — 상수/사전/트리거 테이블
- [ ] `extractor.py` — `extract()` + 헬퍼, 순수 함수
- [ ] `safety_rules.py` — `apply()` + 문맥 보호 치환
- [ ] `evidence_mapper.py` — `map()` + 세그먼트 매칭 헬퍼
- [ ] `structure_service.py` — 위 3개를 순서대로 호출 + DB저장 + 상태전이
- [ ] 테스트: `test_carebase_structure`, `test_evidence_created`, `test_safety_rules_no_forbidden_expression`
- [ ] Mock 문장으로 기대값(§2.4, §4.6) 전부 검증

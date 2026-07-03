# VoiceStruct Core — Phase 2 엔진화 설계 (STT Provider + LLM 구조화)

> 대상: Phase 2 (MVP 이후) — "Mock 탈출"
> 기준: ROADMAP §6 Phase 2, DECISIONS D-05/D-09/D-11, claude-api 레퍼런스
> 목적: 두 교체 축(STT Provider / Domain Extractor)을 실제 구현으로 전환하는 설계

---

## 0. Phase 2의 핵심 = 두 축을 진짜로 교체

MVP에서 "인터페이스만 뚫어둔" 두 지점을 실제 구현으로 채운다.

```
[STT Provider 축]  Mock → CLOVA / RTZR / Google   (입력 정확도)
[Domain 축]        규칙  → Claude API 구조화        (추출 정확도)
```

**전제**: 이 두 모듈은 MVP에서 이미 **순수 함수 + Provider 인터페이스**로 격리돼 있어야 교체가 파일 추가로 끝난다 (ARCHITECTURE, CAREBASE_DESIGN 참고).

---

## 1. STT Provider 추상화 실전화

### 1.1 Provider 인터페이스 확정

```python
# app/providers/base.py
from typing import Protocol
from dataclasses import dataclass

@dataclass
class Segment:
    start_time: float
    end_time: float
    speaker: str | None
    text: str
    confidence: float | None

@dataclass
class TranscriptResult:
    stt_provider: str
    language: str
    raw_transcript: str
    cleaned_transcript: str
    segments: list[Segment]
    confidence_avg: float | None
    stt_status: str          # SUCCESS | FAILED
    duration_sec: float | None

class SttProvider(Protocol):
    name: str
    def transcribe(self, audio_path: str, language: str = "ko-KR") -> TranscriptResult: ...
```

- MVP의 `mock_stt_provider.py`는 이 Protocol을 만족하도록 리팩터 (반환 타입만 맞추면 됨).
- 서비스 계층은 `provider.transcribe(...)`만 호출 → **어떤 Provider든 파이프라인 불변**.

### 1.2 Provider 레지스트리 + 설정

```python
# app/providers/registry.py
from app.core.config import settings

def get_stt_provider() -> SttProvider:
    name = settings.STT_PROVIDER        # "mock" | "clova" | "rtzr" | "google"
    return {
        "mock":   MockSttProvider(),
        "clova":  ClovaSttProvider(settings.CLOVA_API_KEY),
        "rtzr":   RtzrSttProvider(settings.RTZR_API_KEY),
        "google": GoogleSttProvider(settings.GOOGLE_CREDENTIALS),
    }[name]
```

- 환경변수 한 줄(`STT_PROVIDER=clova`)로 전환. 코드 변경 없음.
- `stt_service`는 `get_stt_provider()`만 부르면 됨.

### 1.3 실제 Provider 구현 시 채워야 할 것

MVP Mock이 고정값으로 두던 필드를 실제로 채운다:

| 필드 | Mock | 실제 Provider |
|------|------|---------------|
| segments | 고정 3개 | 실제 화자 분리(diarization) 결과 |
| confidence | 0.9 고정 | STT 엔진 반환값 |
| duration_sec | null | 오디오 실제 길이 |
| cleaned_transcript | 미리 작성 | 후처리(문장 정리) 또는 LLM 정리 |

**Provider별 특성**
- **NAVER CLOVA Speech**: 한국어 최적화, 화자 분리 지원, 장문 비동기 처리
- **RTZR/VITO**: 실시간/스트리밍 강점
- **Google STT**: 다국어, 안정성

### 1.4 비동기 파이프라인 전환 (중요)

실제 STT는 수 초~수십 초 걸림 → 동기 API로 두면 요청이 블로킹됨.

```
POST /api/stt/transcribe → 즉시 202 반환 (status=PROCESSING)
     → 백그라운드 작업(큐)에서 STT 실행
     → 완료 시 status=STT_COMPLETED
클라이언트는 GET /api/audio/{audio_id} 폴링으로 상태 확인
```

- MVP의 `status` 필드가 이미 진행 상태를 표현하므로 **폴링 API로 자연스럽게 연결**.
- 구현: FastAPI `BackgroundTasks`(간단) → Celery/RQ + Redis(확장).
- 상태값에 `STT_PROCESSING`, `STRUCTURE_PROCESSING` 추가 검토.

---

## 2. LLM 구조화 도입 (Claude API)

> **핵심 원칙 (D-05)**: LLM은 extractor를 **교체**하지만 규칙 로직은 **fallback**으로 잔존. LLM 실패/거부 시 규칙 추출로 폴백.

### 2.1 모델 선택

| 용도 | 모델 | 근거 |
|------|------|------|
| **기본 구조화** | `claude-opus-4-8` | 최고 품질, 안전 표현 준수 정확도 높음 |
| **대량/비용 민감** | `claude-sonnet-5` | 추출·요약 등 고volume 워크로드에 비용 효율 ($3/$15 per MTok) |
| 단순 분류만 | `claude-haiku-4-5` | 속도·비용 우선 |

- **기본은 Opus 4.8**로 시작하고, 트래픽 늘면 Sonnet 5로 A/B 후 전환 검토.
- 헬스 인접 도메인이라 **안전 표현 정확도**가 중요 → 초기엔 Opus 권장.

### 2.2 구조화 = Structured Outputs로 스키마 강제 (핵심)

규칙 파싱의 불안정성을 없애기 위해 **Pydantic 스키마로 출력을 강제**한다. `messages.parse()`가 자동 검증까지 해줌.

```python
# app/domains/carebase/llm_extractor.py
import anthropic
from app.schemas.structure_schema import CareBaseStructuredJson  # DB명세 7.4 Pydantic 모델

client = anthropic.Anthropic()   # ANTHROPIC_API_KEY 또는 ant auth login 프로필

SYSTEM = """너는 CareBase Memory 구조화 엔진이다.
음성 전사 텍스트를 CareBase Memory 스키마로 구조화한다.

안전 원칙(반드시 준수):
- 진단·예측·치료 표현 금지 (치매 의심, 인지저하 판정, 질병 진단, 위험 등급, 의학적 조언)
- 대신 "표현 변화 후보", "사용자 자기기록 기반 참고 신호" 등 비진단 표현 사용
- risk_signal_candidates는 REPEATED_QUESTION / TIME_CONFUSION / WORD_FINDING 카테고리만
- 모든 결과는 사용자 확인 전 초안 (requires_user_confirmation=true)
- safety_notice 고정 문구 포함
"""

def extract_with_llm(cleaned_transcript: str, segments: list[dict]) -> CareBaseStructuredJson:
    resp = client.messages.parse(
        model="claude-opus-4-8",
        max_tokens=4096,
        system=SYSTEM,
        output_format=CareBaseStructuredJson,   # ← 스키마 강제 + 자동 파싱/검증
        messages=[{
            "role": "user",
            "content": f"전사 정리본:\n{cleaned_transcript}\n\n세그먼트:\n{segments}",
        }],
    )
    if resp.parsed_output is None:               # 거부/파싱 실패
        raise LlmStructureError()
    return resp.parsed_output
```

- `output_format=PydanticModel` → 응답이 스키마를 반드시 따름 → `json.loads` + 수동 검증 불필요.
- **주의**: `temperature`/`top_p`/`top_k`는 Opus 4.8/Sonnet 5에서 제거됨(400). 넣지 말 것.
- 확장 사고가 필요하면 `thinking={"type":"adaptive"}` 추가 (선택).

### 2.3 규칙 fallback 구조

```python
# app/domains/carebase/extractor.py (Phase 2)
def extract(cleaned_transcript, segments):
    if settings.USE_LLM_EXTRACTOR:
        try:
            draft = llm_extractor.extract_with_llm(cleaned_transcript, segments).model_dump()
        except (LlmStructureError, anthropic.APIError):
            draft = rule_extractor.extract(cleaned_transcript, segments)  # ← MVP 규칙 재사용
    else:
        draft = rule_extractor.extract(cleaned_transcript, segments)
    return safety_rules.apply(draft)   # 안전 규칙은 LLM 결과에도 반드시 재적용 (2중 방어)
```

> **안전 규칙 2중화**: LLM이 실수로 금지 표현을 낼 수 있으므로, `safety_rules.apply()`를 LLM 출력에도 **반드시** 통과시킨다 (D-05, 헬스 리스크).

### 2.4 Claude API 운영 주의사항 (레퍼런스 반영)

- **인증**: `ANTHROPIC_API_KEY` 또는 `ant auth login` 프로필. 코드에 키 하드코딩 금지 → `config.py`에서 환경변수로.
- **에러 처리**: `anthropic.RateLimitError`(429) → 백오프 재시도(SDK 기본 2회), `anthropic.APIError` → fallback. 타입별 예외 체인으로.
- **비용 관리**: 
  - 시스템 프롬프트(안전 원칙)를 **prompt caching**으로 캐시 → 반복 호출 비용 90% 절감
  - `count_tokens()`로 사전 비용 추정
  - 대량이면 **Batch API**(50% 할인, 비실시간)
- **비결정성**: LLM은 매번 다른 출력 → 테스트는 스키마 준수/필드 존재만 검증하고, 값 완전일치 assert는 규칙 extractor에만.

### 2.5 Evidence Mapping 고도화

MVP는 "부분 문자열 포함" 매칭. Phase 2는 LLM이 원문 span을 직접 반환:

```python
# LLM 출력에 evidence span 포함 요청
class FieldEvidence(BaseModel):
    field_name: str
    field_value: str
    evidence_char_start: int    # cleaned_transcript 내 문자 offset
    evidence_char_end: int
# → char offset을 segment 시간(start/end)에 매핑
```

- 정확도↑, 다국어/의역에도 대응. Citations API 활용도 검토.

---

## 3. Phase 2 완료 시 달라지는 것

| 항목 | MVP | Phase 2 |
|------|-----|---------|
| STT | Mock 고정 | 실제 음성 → CLOVA/RTZR/Google |
| 화자 분리 | 없음(speaker_1 고정) | 실제 diarization |
| 구조화 | 규칙 사전 매칭 | Claude API + 규칙 fallback |
| Evidence | 부분 문자열 | LLM char-span → 시간 매핑 |
| 처리 방식 | 동기 | 비동기 큐 + 폴링 |
| risk 감지 | TIME_CONFUSION만 | + REPEATED_QUESTION, WORD_FINDING |
| 안전 규칙 | 1차(생성 시) | 2중(LLM 출력 재검사) |

---

## 4. Phase 2 착수 체크리스트

- [x] `providers/base.py` — `SttProvider` Protocol + `TranscriptResult` 확정
      (segments는 파이프라인 일관성 위해 list[dict]로 확정 — Segment dataclass 대신)
- [x] `mock_stt_provider.py`를 Protocol에 맞게 리팩터 (`MockSttProvider` 클래스 + 계약 테스트 3종)
- [x] `providers/registry.py` + `config.py`에 `STT_PROVIDER` 설정, `stt_service` Provider 경유로 전환
- [ ] 실제 Provider 1종 먼저 (CLOVA 권장 — 한국어) 구현 + 통합 테스트
- [ ] 비동기 파이프라인 (BackgroundTasks → 큐) + `*_PROCESSING` 상태 추가
- [ ] `llm_extractor.py` — Claude API `messages.parse()` + 시스템 프롬프트(안전 원칙)
- [ ] `USE_LLM_EXTRACTOR` 플래그 + 규칙 fallback 경로
- [ ] `safety_rules.apply()` LLM 출력 재적용 검증 (안전 게이트)
- [ ] prompt caching + count_tokens 비용 관리
- [ ] LLM 경로 테스트(스키마 준수) vs 규칙 경로 테스트(값 일치) 분리

---

## 5. 이후(Phase 3) 연결 지점

- 도메인 레지스트리(`domains/registry.py`)로 CareBase 외 119/회의록/상담 확장 → `llm_extractor`의 시스템 프롬프트만 도메인별 교체
- `schema_version` 관리로 `carebase_memory_v1 → v2` 마이그레이션
- 관측성(로깅/트레이싱): STT 지연, LLM 토큰/비용, fallback 발생률 대시보드

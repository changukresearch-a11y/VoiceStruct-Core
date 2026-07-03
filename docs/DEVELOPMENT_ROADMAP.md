# VoiceStruct Core — 개발 로드맵 & 디벨롭 문서

> 기준 문서: `VoiceStruct Core MVP 개발 지시서.xml`, `VoiceStruct Core MVP DB-API 명세서.xml`
> 작성일: 2026-07-03
> 목적: MVP 진행 방향 + 슬라이스 전략 + 고도화 + 추가 기능을 한 문서로 통합

---

## 0. 한눈에 보는 요약

| 구분 | 핵심 |
|------|------|
| **본질** | 개별 STT 서비스가 아니라 "음성 → 목적별 구조화 데이터" **공통 엔진** |
| **MVP 범위** | FastAPI + SQLite + Mock STT + CareBase Memory **단일 도메인** 파이프라인 |
| **핵심 원칙** | ① Mock 우선 ② 사람 확인 기반(AI는 초안) ③ **비진단 안전 표현** |
| **파이프라인** | 업로드 → Mock STT → Transcript → 구조화(AI_TEMP) → Evidence 연결 → 사용자 수정 → 확정 → ChangeLog |
| **다음 단계** | 실제 STT/LLM → 멀티 도메인 → 보호자 대시보드 → 클라우드 |

---

## 1. 프로젝트 본질 재정의 (엔진 관점)

이 프로젝트의 승부처는 CareBase Memory라는 **기능**이 아니라, 음성을 어떤 목적이든 구조화할 수 있는 **엔진 구조**다.

```
         ┌─────────────────────────────────────────────┐
         │              VoiceStruct Core Engine         │
         │                                              │
  음성 → │  [STT Provider] → [Transcript] → [Domain     │ → 구조화 데이터
         │                                   Extractor] │    + 원문 근거(Evidence)
         │                     ↑ 교체 가능      ↑ 교체 가능 │    + 사람 확인 워크플로우
         └─────────────────────────────────────────────┘
                    Mock/CLOVA/RTZR        CareBase/119/회의록/상담
```

**설계의 핵심 = "교체 가능한 두 축"**
- **STT Provider 축**: Mock ↔ CLOVA ↔ RTZR ↔ Google (입력이 바뀌어도 파이프라인 불변)
- **Domain 축**: CareBase Memory ↔ 119 응급 ↔ 회의록 ↔ 상담 (도메인마다 스키마/추출 규칙만 교체)

> MVP에서 이 두 축을 **"지금은 하나지만 나중에 여러 개"** 형태로만 뚫어두면, 이후 확장은 새 파일 추가로 끝난다. 반대로 여기서 하드코딩하면 나중에 전면 리팩터가 온다.

---

## 2. 현재 MVP 스펙 분석

### 2.1 스펙의 강점
- 상태 머신이 명확함 (`AUDIO_RECEIVED → STT_COMPLETED → STRUCTURED → CONFIRMED`)
- **AI 초안 ≠ 최종 기록** 원칙이 데이터 모델에 반영됨 (`ai_structured_json` vs `user_confirmed_json`)
- 원문 근거(Evidence) + 변경 이력(ChangeLog)로 **추적성(traceability)** 확보
- 안전 표현 원칙이 별도 모듈(`safety_rules.py`)로 분리됨 → 헬스케어 인접 도메인에서 필수

### 2.2 구현 전에 정리하면 좋을 스펙 상 불일치/모호점

| # | 위치 | 내용 | 권장 처리 |
|---|------|------|-----------|
| 1 | 지시서 7.1 vs DB명세 3.1 | `AudioRecord`에 `updated_at` 필드 유무가 다름 (DB명세에는 있음) | **`updated_at` 포함**으로 통일 (상태 전이 시각 추적에 유용) |
| 2 | 구조화 응답 키 | `POST /structure/run`은 `structured_json`, `GET`은 `ai_structured_json` | 내부 저장 컬럼은 `ai_structured_json`, 응답 키는 스펙대로 각각 유지하되 **문서에 명시** |
| 3 | `evidence_count` | 예시는 4, 테스트 기준은 `>= 3` | 규칙상 생성되는 개수는 가변 → 테스트는 `>= 3` 유지 (문제 없음) |
| 4 | `INVALID_STATUS_TRANSITION` | 에러 코드는 정의됐지만 MVP 플로우에서 강제 안 함 | MVP는 최소 검증(확정 후 수정 금지)만, 코드는 미리 정의만 |
| 5 | `people`/`places` 추출 | 규칙 기반이라 MVP 문장 외엔 정확도 낮음 | MVP는 규칙 OK, **고도화에서 LLM/NER 교체 지점**으로 표시 |
| 6 | `confirmed_by` | 저장 안 함 (추후 `UserConfirmationLog`) | MVP는 무시, 스키마에 확장 주석만 남김 |
| 7 | 시간대 | 서버 로컬 시간 사용, 추후 UTC 전환 | `datetime.utcnow()` 대신 **유틸 함수 1곳**으로 감싸 두면 전환 1줄 |

> 위 항목들은 "지금 고쳐라"가 아니라 **구현 시작 전 합의해 둘 결정 사항**. 대부분 기본값이 명확해서 바로 진행 가능.

---

## 3. 개발 진행 방향 (아키텍처 원칙)

지시서의 개발 순서(Step 1~17)는 **수평 레이어 순서**(모델 전부 → API 전부)라 "끝까지 가봐야 동작 확인"이 되는 단점이 있다. 아래 원칙으로 **수직 슬라이스**로 바꿔 진행하는 걸 권장.

1. **Walking Skeleton 우선** — 서버가 뜨고 `GET /`가 응답하는 최소 골격부터. (Step 1~2)
2. **한 번에 한 슬라이스, 끝까지** — 각 슬라이스는 API → 서비스 → 리포지토리 → 모델 → 테스트까지 세로로 관통.
3. **상수/유틸 먼저 고정** — `constants.py`(상태값·에러코드·도메인), `json_utils.py`(dumps/loads), `id_utils.py`(ID 생성)를 초반에 만들어 전 레이어가 공유.
4. **레이어 경계 지키기** — 라우터는 얇게(검증+응답), 비즈니스는 서비스, DB 접근은 리포지토리. 안전 규칙/추출은 도메인 모듈.
5. **에러는 도메인 예외 → 핸들러 1곳** — 서비스는 `AudioNotFoundError` 같은 예외를 던지고, FastAPI `exception_handler`가 공통 에러 포맷(`{ok:false, error:{code,message}}`)으로 변환.
6. **Provider/Domain은 인터페이스 1개 + 구현 1개** — 과한 추상화 금지(지시서 18.2), 단 함수 시그니처만 교체 가능하게.

### 권장 최종 폴더 구조 (지시서 구조 + 유틸 보강)
```
voicestruct-core/
  app/
    main.py
    core/
      config.py        # 설정 (pydantic-settings)
      database.py      # SQLite 엔진/세션
      constants.py     # 상태값·에러코드·도메인 상수
      json_utils.py    # dumps/loads (ensure_ascii=False)
      id_utils.py      # audio_/transcript_ ... ID 생성  ← 보강
      exceptions.py    # 도메인 예외 + 핸들러          ← 보강
      time_utils.py    # now() 래퍼 (UTC 전환 대비)     ← 보강
    api/               # audio / stt / structure routes
    models/            # SQLAlchemy 5종
    schemas/           # Pydantic 요청·응답
    services/          # 비즈니스 로직 5종
    repositories/      # DB 접근 5종
    providers/         # mock_stt_provider.py (+ base.py)
    domains/carebase/  # schema / extractor / safety_rules / evidence_mapper
  tests/
  storage/audio/
  docs/                # api_spec.md, mvp_notes.md, 이 로드맵
  requirements.txt
  README.md
```

---

## 4. 수직 슬라이스 전략 (권장 구현 순서)

각 슬라이스 = "돌아가고 + 테스트 통과하는" 최소 단위. 슬라이스마다 커밋.

| Slice | 목표 | 완료 판정(테스트) |
|-------|------|-------------------|
| **S0. 골격** | 프로젝트 생성, DB 연결, `GET /`, 상수/유틸/예외핸들러 | `test_health_check` |
| **S1. 업로드** | `POST /api/audio/upload` → 파일 저장 + `AudioRecord` 생성 | `test_audio_upload_success`, `..._invalid_domain` |
| **S2. Mock STT** | `POST /api/stt/transcribe` → `TranscriptRecord` + 상태 전이 | `test_mock_stt_success`, `..._audio_not_found` |
| **S3. 구조화+Evidence** | `POST /api/structure/run` → extractor + safety + evidence + `STRUCTURED` | `test_structure_run_success`, `test_evidence_created`, `test_safety_rules...` |
| **S4. 조회** | `GET /structure/{id}`, `.../evidence` | 조회 응답 검증 |
| **S5. 수정** | `PATCH /structure/{id}` → 병합 + `USER_EDITED` + ChangeLog | `test_structure_update_success`, `test_change_log_created` |
| **S6. 확정** | `POST /structure/{id}/confirm` → `USER_CONFIRMED` + Audio `CONFIRMED` (멱등) | `test_confirm_success`, `test_confirm_idempotent`, `test_update_already_confirmed_rejected` |
| **S7. 마감** | `GET /structure/{id}/changes`, README, 전체 pytest green | 전체 통과 + README 실행 재현 |

> **왜 이 순서?** 각 슬라이스가 이전 슬라이스의 산출물(audio_id → transcript_id → structured_id)을 입력으로 쓰므로, 파이프라인 순서 그대로가 곧 의존성 순서. S3까지만 가도 "음성→구조화" 데모가 된다.

---

## 5. MVP 구현 상세 체크리스트

### 5.1 핵심 도메인 로직 (규칙 기반, MVP)
- [ ] `extractor.py` — people/places/time_reference/emotion/risk_signal_candidates 규칙 추출 + `missing_fields` 계산
- [ ] `safety_rules.py` — 금지 표현 검사 후 안전 표현 치환 (`치매 의심→표현 변화 후보` 등), `safety_notice` 고정 삽입
- [ ] `evidence_mapper.py` — segment.text 포함 매칭으로 필드별 Evidence 생성 (people/places/time_reference/emotion/risk)
- [ ] `mock_stt_provider.py` — 고정 STT 결과 반환 (confidence_avg 0.9, segment 3개)

### 5.2 서비스 계층 규칙 (놓치기 쉬운 것)
- [ ] STT 실행 전 `AudioRecord.status`가 `AUDIO_RECEIVED`/`FAILED`인지 검증
- [ ] 확정 후 PATCH → **409 `ALREADY_CONFIRMED`**
- [ ] 재확정 → **멱등 200** (`message: "이미 확정된 기록입니다."`)
- [ ] PATCH 병합 기준: `user_confirmed_json` 있으면 그것, 없으면 `ai_structured_json`
- [ ] Safety Rules는 **run + patch 두 시점 모두** 적용
- [ ] 존재하지 않는 audio/transcript/structured → 404 + 해당 에러코드

### 5.3 완료 기준(DoD)
지시서 16장 + DB명세 14장의 항목 전부 + `pytest` green + `README`만으로 로컬 실행/API 테스트 재현.

---

## 6. 개발 고도화 로드맵 (Post-MVP)

### Phase 2 — 실제 엔진화 (Mock 탈출)
- **STT Provider 추상화 실전화**: `providers/base.py`에 `transcribe(audio_path) -> TranscriptResult` 인터페이스 확정
  - `naver_clova_provider.py`, `rtzr_provider.py`, `google_stt_provider.py` 순차 추가
  - **화자 분리(diarization)**, 실제 `confidence`, `duration_sec` 채우기
  - 실패/재시도/타임아웃/요금 로깅
- **LLM 구조화 도입**: `domains/carebase/extractor.py`를 규칙 → **LLM 프롬프트 기반**으로 교체 (Claude API)
  - 규칙 추출은 **fallback**으로 유지 (LLM 실패 시)
  - **구조화 스키마를 tool/JSON schema로 강제** → 파싱 안정화
  - Evidence도 LLM이 원문 span을 반환하도록 (문자 offset + segment 시간 매핑)
- **비동기 파이프라인**: 업로드 후 STT/구조화를 백그라운드 작업(큐)으로. `status`가 이미 진행 상태를 표현하므로 폴링 API로 연결.

### Phase 3 — 멀티 도메인 엔진
- `domains/` 하위에 도메인 플러그인 등록 방식 (`registry`)
  - `emergency_119/` — 위치·증상·연락처·시간 구조화 (안전 등급 아님, 정보 정리만)
  - `meeting/` — 안건·결정사항·담당자·기한(action item)
  - `counseling/` — 주제·감정·리스크 신호(비진단)
- `domain` 값 화이트리스트를 상수/설정에서 관리, API는 도메인별 스키마 자동 선택
- **schema_version 관리 체계** — `carebase_memory_v1 → v2` 마이그레이션 정책

### Phase 4 — 서비스화
- **인증/권한**: 로그인, 사용자, **보호자 권한(피보호자-보호자 관계)**, 기록 접근 제어
- **프론트엔드**: 업로드 → 구조화 초안 확인 → **원문 근거 하이라이트** → 수정 → 확정 UX
- **보호자 대시보드**: 시계열 변화, 확인 필요 신호 모음, 알림
- **클라우드 배포**: Postgres 전환, 오브젝트 스토리지(S3), 컨테이너, CI/CD
- **실시간 스트리밍 STT** (WebSocket)

---

## 7. 추가 기능 백로그 (우선순위 제안)

| 우선 | 기능 | 설명 | 근거 |
|------|------|------|------|
| ★★★ | **REPEATED_QUESTION 감지** | 세션 간/내 반복 표현 후보 추적 | 스펙에 카테고리만 있고 미구현 |
| ★★★ | **WORD_FINDING 감지** | "그거", "뭐더라" 등 단어 찾기 어려움 후보 | 스펙 카테고리 미구현 |
| ★★★ | **시계열 변화 트렌드** | 확정된 기록들을 시간축으로 집계 → 보호자 참고 신호 | 엔진의 진짜 가치 |
| ★★☆ | **UserConfirmationLog** | 확정자/시각/코멘트 감사 추적 | 스펙에 확장 예고됨 |
| ★★☆ | **PDF/문서 리포트 내보내기** | 확정 기록을 보호자용 리포트로 export | 활용도 |
| ★★☆ | **개인정보/민감정보 마스킹** | 전화번호·주소·주민번호 비식별화 | 헬스 인접, 규제 대비 |
| ★★☆ | **Soft delete + 감사 로그** | 삭제 대신 비활성화, 전 이력 보존 | 추적성 원칙과 일관 |
| ★☆☆ | **다국어(language) 확장** | ko-KR 외 STT/구조화 | 확장성 |
| ★☆☆ | **재구조화(re-run)** | 더 나은 모델로 기존 transcript 재구조화(버전업) | schema_version과 연계 |
| ★☆☆ | **RAG 기반 회상 보조** | 과거 확정 기록을 검색해 맥락 제공 | Memory 도메인 특성 |

---

## 8. 도메인 확장 설계 (엔진 플러그인화)

MVP에서 이 형태로만 뚫어두면 도메인 추가가 파일 추가로 끝난다.

```python
# app/domains/base.py  (Phase 2에서 도입)
class DomainExtractor(Protocol):
    domain: str
    schema_version: str
    def extract(self, cleaned_transcript: str, segments: list[dict]) -> dict: ...
    def evidence_fields(self) -> list[str]: ...

# app/domains/registry.py
DOMAIN_REGISTRY: dict[str, DomainExtractor] = {
    "carebase_memory": CareBaseExtractor(),
    # "emergency_119": Emergency119Extractor(),   ← 추가만 하면 됨
}
```
- 서비스는 `DOMAIN_REGISTRY[domain]`으로 추출기 선택 → API 로직 불변
- Safety Rules도 도메인별로 다를 수 있으니 도메인 모듈 안에 둠

---

## 9. 데이터 · 보안 · 프라이버시 · 안전

- **안전 표현(비진단) 원칙**: 이 도메인의 법적/윤리적 생명줄. `safety_rules.py` 테스트를 CI 필수 게이트로.
- **민감정보**: 음성/전사에는 이름·질병·위치가 섞임 → 접근 로그, 암호화 저장(고도화), 마스킹 옵션.
- **동의(consent)**: 실서비스 전환 시 녹음/저장 동의 기록 모델 필요.
- **데이터 보존/삭제 정책**: soft delete + 보존기간.
- **감사 추적**: ChangeLog는 이미 있음 → 확정/조회/삭제까지 확장.
- **DB 전환 대비**: MVP는 SQLite지만 `database.py` 세션 계층만 갈아끼우면 Postgres로. ForeignKey는 MVP엔 미강제(스펙)지만 Phase 2에서 실제 FK로 승격.

---

## 10. 테스트 · 품질 · CI

- **MVP 필수 테스트**(DB명세 12장 14종) 전부 → 슬라이스별로 나눠 작성.
- **안전 규칙 테스트**를 별도 강조: 금지 표현이 부적절 문맥에서 새어나가지 않는지.
- **픽스처**: 인메모리 SQLite(`sqlite:///:memory:`) + `TestClient`로 API E2E.
- **Phase 2+**: GitHub Actions CI (lint `ruff` + `pytest` + 커버리지), pre-commit.
- **계약 테스트**: Provider/Domain 인터페이스 구현체가 계약을 지키는지.

---

## 11. 지금 결정하면 좋은 사항 (Open Questions)

1. `AudioRecord.updated_at` 포함 여부 → **포함 권장**
2. 실제 LLM 도입 시점 → MVP는 규칙, **Phase 2에서 Claude API** 권장
3. ID 생성: `timestamp+short_uuid` 형식 확정(스펙대로) — `id_utils.py` 1곳
4. DB 전환 목표 시점(Postgres) — 배포 직전
5. 도메인 2번째 후보 우선순위 — 119 vs 회의록 (사업 목표에 따라)

---

## 12. 다음 단계 제안

**바로 시작 가능한 것:**
1. `requirements.txt` + 폴더 골격 + `core/`(constants, database, json_utils, id_utils, exceptions) 생성 → **Slice 0**
2. Slice 1~2 (업로드 + Mock STT) 구현 + 테스트
3. Slice 3 (구조화 + Evidence + Safety) — 프로젝트의 심장부
4. Slice 4~7 마무리 + README

> 원하면 이 로드맵대로 **Slice 0부터 실제 코드로 스캐폴딩** 시작할게. "S0부터 만들어줘" 하면 돌아가는 FastAPI 골격부터 세울게.

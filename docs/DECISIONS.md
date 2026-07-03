# VoiceStruct Core — 확정 결정서 (Decision Log)

> 기준: `개발 지시서.xml`, `DB-API 명세서.xml`, `docs/DEVELOPMENT_ROADMAP.md`
> 확정일: 2026-07-03
> 규칙: **여기 적힌 결정이 두 명세서와 충돌하면 이 문서가 우선한다.** 새 결정은 아래에 계속 append.

---

## A. 스펙 불일치 확정 (로드맵 2.2 대응)

### D-01. `AudioRecord.updated_at` — ✅ **포함**
- **결정**: `audio_records` 테이블에 `updated_at: DateTime, nullable` 추가 (DB명세 3.1 기준으로 통일).
- **이유**: 상태 전이(`AUDIO_RECEIVED→STT_COMPLETED→STRUCTURED→CONFIRMED`) 시각 추적 → 디버깅·감사 유리. 컬럼 1개라 비용 무시 가능.
- **구현 규칙**: 상태를 바꾸는 모든 서비스(STT 완료, 구조화 완료, 확정)에서 `updated_at = now()` 갱신.
- **영향 파일**: `app/models/audio_record.py`, `app/repositories/audio_repository.py`

### D-02. 구조화 응답 키 이름 (`structured_json` vs `ai_structured_json`) — ✅ **둘 다 스펙대로 유지 + 규칙 명문화**
- **결정**:
  - DB 컬럼명 = `ai_structured_json` (AI/Mock 초안), `user_confirmed_json` (수정·확정본)
  - `POST /api/structure/run` **응답 키** = `structured_json` (스펙 6.4대로, 방금 만든 초안을 그대로 반환)
  - `GET /api/structure/{id}` **응답 키** = `ai_structured_json` + `user_confirmed_json` (스펙 6.5대로 둘 다 노출)
- **이유**: 두 명세서 예시가 이미 이렇게 정의됨. 임의 통일보다 스펙 준수가 프론트/테스트 계약에 안전.
- **주의**: 코드에서 "응답 key"와 "DB 컬럼명"을 헷갈리지 말 것. 스키마(Pydantic) 필드명으로 강제.

### D-03. `evidence_count` 값 — ✅ **가변, 테스트는 `>= 3`**
- **결정**: `run` 응답의 `evidence_count`는 실제 생성된 EvidenceRecord 수(가변). 예시의 4는 예시일 뿐.
- **테스트 기준**: `EvidenceRecord count >= 3` (DB명세 12.2), 최소 `people`/`places`/`time_reference` 포함.

### D-04. `INVALID_STATUS_TRANSITION` 에러코드 — ✅ **상수만 정의, MVP 미강제**
- **결정**: `constants.py`에 에러코드 문자열만 정의. MVP에서 강제하는 상태 검증은 아래 2개만:
  1. STT 실행 시 `AudioRecord.status ∈ {AUDIO_RECEIVED, FAILED}` (DB명세 6.3 처리순서 2)
  2. 확정 후 PATCH → `409 ALREADY_CONFIRMED`
- **이유**: MVP 과설계 금지(지시서 18.2). 전체 상태머신 엄격 검증은 Phase 2.

### D-05. `people`/`places`/`emotion` 규칙 기반 추출 — ✅ **MVP는 규칙, LLM은 Phase 2 교체 지점**
- **결정**: MVP `extractor.py`는 DB명세 8.2 규칙(사전 매칭)만 사용. Mock 문장 기준으로 테스트 기대값 충족.
- **표시**: `extractor.py` 상단에 `# NOTE: Phase 2에서 LLM 추출로 교체, 규칙은 fallback 유지` 주석 명시.
- **관련**: → **D-09**(구조화 방식 확정)

### D-06. `confirmed_by` 저장 — ✅ **MVP 미저장, 확장 예약**
- **결정**: `confirm` API는 `confirmed_by`를 받되 별도 테이블 저장 안 함(DB명세 6.7). `confirmed_at`만 기록.
- **확장 예약**: Phase 2에서 `UserConfirmationLog(confirm_id, structured_id, confirmed_by, confirmed_at, comment)` 도입.
- **표시**: confirmation_service에 `# TODO(Phase2): UserConfirmationLog` 주석.

### D-07. 시간대(timezone) — ✅ **로컬 시간 + `time_utils.now()` 래퍼 경유**
- **결정**: MVP는 서버 로컬 시간. **단 모든 시각 생성은 `app/core/time_utils.py`의 `now()` 한 곳만 사용**.
- **이유**: 추후 UTC 전환을 함수 1개 수정으로 끝내기 위함(DB명세 2.2).
- **저장 포맷**: SQLite에는 ISO datetime 문자열 허용(DB명세 2.2).

---

## B. 열린 질문 확정 (로드맵 11장 대응)

### D-08. 보강 유틸 파일 3종 — ✅ **채택**
- **결정**: 지시서 기본 구조에 아래 3개 추가.
  - `app/core/id_utils.py` — `audio_/transcript_/structured_/evidence_/change_` + `{timestamp}_{short_uuid}` 생성 (DB명세 2.1 형식)
  - `app/core/exceptions.py` — 도메인 예외 클래스 + FastAPI `exception_handler`로 공통 에러 포맷(`{ok:false, error:{code,message}}`) 변환
  - `app/core/time_utils.py` — `now()` 래퍼 (D-07)
- **이유**: ID 생성·에러 변환·시각 로직이 서비스마다 중복되는 것 방지. 지시서 13.3(json_utils)과 같은 취지의 확장.
- **원칙 준수**: 인터페이스 최소, 과한 추상화 없음(지시서 18.2).

### D-09. 구조화 방식 — ✅ **MVP는 규칙 기반만, 실제 LLM은 Phase 2**
- **결정**: MVP extractor = 규칙+Mock. Claude API 구조화는 Phase 2에서 도입하며 규칙 로직은 fallback으로 잔존.
- **이유**: 지시서 5.3/18 "Mock 우선" 원칙. 범위 명확·API키/비용/비결정성 테스트 문제 회피.
- **Phase 2 설계 방향**: 구조화 스키마를 tool/JSON schema로 강제해 파싱 안정화, Evidence는 원문 span 반환.

### D-10. ID 생성 형식 — ✅ **`{prefix}_{YYYYMMDD_HHMMSS}_{short_uuid}`**
- **결정**: DB명세 2.1 형식 그대로. 예) `audio_20260703_153012_a1b2c3`.
- **구현**: `id_utils.py`에서 `short_uuid = uuid4().hex[:6]`, timestamp는 `time_utils.now()` 기반.
- **주의**: 외부 API는 문자열 ID, DB 내부 PK는 `id: int autoincrement` 병행(DB명세 2.1).

### D-11. DB 전환(SQLite→Postgres) 시점 — ✅ **배포 직전(Phase 4)**
- **결정**: MVP~Phase 3는 SQLite. `app/core/database.py`의 세션/엔진 계층만 교체 가능하게 격리.
- **FK 정책**: MVP는 FK 미강제(DB명세 4.2), 서비스 레이어에서 연결 ID 존재 검증. Phase 2에서 실제 FK 승격 검토.

### D-12. 2차 도메인 우선순위 — ⏸ **미정 (MVP 검증 후 결정)**
- **결정**: 지금 결정하지 않음. **엔진을 도메인 중립적으로만 설계**해 어떤 도메인이 와도 붙도록 준비.
- **준비 사항**: `domains/` 플러그인 레지스트리 구조를 Phase 3 시작 시 도입(로드맵 8장). MVP에서는 `carebase_memory` 하드코딩 최소화(도메인 값을 상수/화이트리스트로).
- **재검토 시점**: MVP 완료 + 데모 후.

---

## C. 확정 기준으로 갱신된 "MVP 최종 데이터 모델" 요약

변경점(D-01) 반영한 5개 테이블 최종형:

| 테이블 | 확정 컬럼 요점 |
|--------|----------------|
| `audio_records` | id, audio_id(uq), user_id, domain, file_name, file_path, file_type, duration_sec(null), status, created_at, **updated_at(null) ← D-01** |
| `transcript_records` | id, transcript_id(uq), audio_id, stt_provider, language, raw_transcript, cleaned_transcript, segments_json, confidence_avg(null), stt_status, created_at |
| `structured_records` | id, structured_id(uq), audio_id, transcript_id, domain, schema_version, ai_structured_json, user_confirmed_json(null), status, created_at, updated_at(null), confirmed_at(null) |
| `evidence_records` | id, evidence_id(uq), structured_id, field_name, field_value, evidence_text, start_time(null), end_time(null), speaker(null), confidence(null), created_at |
| `change_logs` | id, change_id(uq), structured_id, changed_fields_json, previous_value_json, new_value_json, changed_by, created_at |

**상수 확정** (`app/core/constants.py`):
- `DOMAIN_CAREBASE = "carebase_memory"`, `ALLOWED_DOMAINS = {DOMAIN_CAREBASE}`
- Audio status: `AUDIO_RECEIVED, STT_COMPLETED, STRUCTURED, CONFIRMED, FAILED`
- Structured status: `AI_TEMP, USER_EDITED, USER_CONFIRMED, REJECTED, NEEDS_REVIEW`
- STT status: `SUCCESS, FAILED`
- Error codes: `INVALID_DOMAIN, AUDIO_NOT_FOUND, TRANSCRIPT_NOT_FOUND, STRUCTURED_RECORD_NOT_FOUND, ALREADY_CONFIRMED, FILE_UPLOAD_FAILED, STT_FAILED, STRUCTURE_FAILED, EVIDENCE_NOT_FOUND, INVALID_STATUS_TRANSITION, INTERNAL_SERVER_ERROR`
- Schema version: `carebase_memory_v1`
- Risk categories: `REPEATED_QUESTION, TIME_CONFUSION, WORD_FINDING` (MVP 감지 = `TIME_CONFUSION`만)

---

## D. 확정된 스코프 경계 (다시 못 박기)

**MVP 포함**: 업로드·MockSTT·구조화(규칙)·Evidence·수정·확정·ChangeLog·조회·안전규칙·pytest·README
**MVP 제외**: 실제 STT/LLM, 프론트, 로그인/보호자 권한, 119/회의록/상담, 클라우드, 스트리밍, 의료 진단·예측

---

## 결정 요약 (한 줄)

| ID | 항목 | 확정 |
|----|------|------|
| D-01 | AudioRecord.updated_at | 포함 |
| D-02 | 응답 키 이름 | 스펙대로(run=structured_json / get=ai_structured_json) |
| D-03 | evidence_count | 가변, 테스트 ≥3 |
| D-04 | INVALID_STATUS_TRANSITION | 상수만, MVP 미강제 |
| D-05 | 규칙 추출 | MVP 규칙, LLM은 Phase2 |
| D-06 | confirmed_by | 미저장, 확장 예약 |
| D-07 | timezone | 로컬+now() 래퍼 |
| D-08 | 유틸 3종 | 채택 |
| D-09 | 구조화 방식 | 규칙 기반만 |
| D-10 | ID 형식 | prefix_timestamp_shortuuid |
| D-11 | DB 전환 | 배포 직전(Phase4) |
| D-12 | 2차 도메인 | 미정(중립 설계) |

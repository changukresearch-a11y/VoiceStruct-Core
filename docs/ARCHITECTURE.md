# VoiceStruct Core — 아키텍처 & 배관 설계 (에러·상태머신·계층·유틸)

> 대상: `app/core/*`, `app/services/*`, `app/repositories/*`, `app/main.py`
> 기준: DB-API 명세서 4~6장, DECISIONS.md, ROADMAP §3
> 목적: 모든 API가 공유하는 횡단 관심사(cross-cutting)를 구현 직전 수준으로 확정

---

## 0. 계층 책임 분리 (한 장 요약)

```
HTTP 요청
  │
  ▼
[api/*_routes.py]  라우터 — 얇게: 요청 파싱, Pydantic 검증, 서비스 호출, 응답 직렬화
  │  (도메인 예외를 던지면 아래 핸들러가 잡음)
  ▼
[services/*.py]    서비스 — 비즈니스 규칙: 존재검증, 상태검증, 트랜잭션 오케스트레이션
  │
  ├─▶ [domains/carebase/*]  순수 계산 (extract/safety/evidence)   ← CAREBASE_DESIGN.md
  ├─▶ [providers/*]         Mock STT
  └─▶ [repositories/*.py]   레포 — DB 접근만: CRUD, 쿼리. 비즈니스 판단 없음
        │
        ▼
      [core/database.py]   SQLAlchemy 세션/엔진
```

**철칙**
- 라우터에 `if not found: raise HTTPException(...)` 흩뿌리지 말 것 → 서비스가 **도메인 예외**를 던지고, **핸들러 1곳**이 HTTP로 변환.
- 레포는 "찾으면 객체 / 없으면 None" 반환. **404 판단은 서비스**가.
- 상태 전이 규칙은 서비스에 모음(도메인 예외로 위반 표현).

---

## 1. core/exceptions.py — 예외 계층 + 핸들러

### 1.1 예외 계층

```python
# app/core/exceptions.py
from app.core import constants as C

class VoiceStructError(Exception):
    """모든 도메인 예외의 부모. code/message/http_status를 표준화."""
    code: str = C.INTERNAL_SERVER_ERROR
    http_status: int = 500
    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)
    default_message = "서버 내부 오류가 발생했습니다."

class InvalidDomainError(VoiceStructError):
    code = C.INVALID_DOMAIN; http_status = 400
    default_message = "MVP에서는 carebase_memory 도메인만 지원합니다."

class AudioNotFoundError(VoiceStructError):
    code = C.AUDIO_NOT_FOUND; http_status = 404
    default_message = "해당 audio_id를 찾을 수 없습니다."

class TranscriptNotFoundError(VoiceStructError):
    code = C.TRANSCRIPT_NOT_FOUND; http_status = 404
    default_message = "해당 transcript_id를 찾을 수 없습니다."

class StructuredRecordNotFoundError(VoiceStructError):
    code = C.STRUCTURED_RECORD_NOT_FOUND; http_status = 404
    default_message = "해당 structured_id를 찾을 수 없습니다."

class AlreadyConfirmedError(VoiceStructError):
    code = C.ALREADY_CONFIRMED; http_status = 409
    default_message = "이미 확정된 구조화 기록은 수정할 수 없습니다."

class FileUploadError(VoiceStructError):
    code = C.FILE_UPLOAD_FAILED; http_status = 500
    default_message = "파일 업로드 중 오류가 발생했습니다."

class SttError(VoiceStructError):
    code = C.STT_FAILED; http_status = 500
    default_message = "Mock STT 처리 중 오류가 발생했습니다."

class StructureError(VoiceStructError):
    code = C.STRUCTURE_FAILED; http_status = 500
    default_message = "CareBase 구조화 처리 중 오류가 발생했습니다."

class InvalidStatusTransitionError(VoiceStructError):
    code = C.INVALID_STATUS_TRANSITION; http_status = 409
    default_message = "허용되지 않은 상태 전이입니다."   # D-04: 정의만, MVP 거의 미사용
```

### 1.2 공통 에러 핸들러 (main.py 등록)

```python
# app/core/exceptions.py (이어서)
from fastapi import Request
from fastapi.responses import JSONResponse

async def voicestruct_exception_handler(request: Request, exc: VoiceStructError):
    return JSONResponse(
        status_code=exc.http_status,
        content={"ok": False, "error": {"code": exc.code, "message": exc.message}},
    )

def register_exception_handlers(app):
    app.add_exception_handler(VoiceStructError, voicestruct_exception_handler)
    # 예상 못한 예외 → 500 표준 포맷
    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": {
                "code": C.INTERNAL_SERVER_ERROR,
                "message": "서버 내부 오류가 발생했습니다."}},
        )
```

> **효과**: 서비스는 `raise AudioNotFoundError()` 한 줄만. 응답 포맷(`{ok:false, error:{code,message}}`, DB명세 5.2)은 자동. 라우터에 try/except 반복 제거.

### 1.3 에러코드 ↔ HTTP ↔ 예외 매핑표 (DB명세 5.3/5.4)

| 예외 | code | HTTP | 발생 시점 |
|------|------|------|-----------|
| InvalidDomainError | INVALID_DOMAIN | 400 | 업로드·구조화에서 domain≠carebase_memory |
| AudioNotFoundError | AUDIO_NOT_FOUND | 404 | STT 실행 시 audio 없음 |
| TranscriptNotFoundError | TRANSCRIPT_NOT_FOUND | 404 | 구조화 시 transcript 없음 |
| StructuredRecordNotFoundError | STRUCTURED_RECORD_NOT_FOUND | 404 | 조회·수정·확정·evidence·changes |
| AlreadyConfirmedError | ALREADY_CONFIRMED | 409 | 확정 후 PATCH |
| FileUploadError | FILE_UPLOAD_FAILED | 500 | 파일 저장 실패 |
| SttError | STT_FAILED | 500 | Mock STT 예외 |
| StructureError | STRUCTURE_FAILED | 500 | extractor/mapper 예외 |
| — | INTERNAL_SERVER_ERROR | 500 | 미분류 |

---

## 2. 상태 머신 (State Machine)

### 2.1 AudioRecord 상태 (DB명세 3.1)

```
AUDIO_RECEIVED ──STT성공──▶ STT_COMPLETED ──구조화──▶ STRUCTURED ──확정──▶ CONFIRMED
      │                          │                        │
      └────────실패──▶ FAILED ◀──┴────────실패────────────┘
```

전이 트리거(서비스별):
| 전이 | 발생 API | 담당 서비스 |
|------|----------|-------------|
| (신규)→AUDIO_RECEIVED | POST /audio/upload | audio_service |
| AUDIO_RECEIVED→STT_COMPLETED | POST /stt/transcribe | stt_service |
| STT_COMPLETED→STRUCTURED | POST /structure/run | structure_service |
| STRUCTURED→CONFIRMED | POST /structure/{id}/confirm | confirmation_service |
| *→FAILED | 각 단계 예외 시 | 해당 서비스 |

### 2.2 StructuredRecord 상태 (DB명세 3.3)

```
AI_TEMP ──PATCH──▶ USER_EDITED ──confirm──▶ USER_CONFIRMED
   │                                  ▲
   └──────────confirm(수정없이)────────┘

USER_CONFIRMED 에서 PATCH → 409 ALREADY_CONFIRMED (전이 거부)
REJECTED / NEEDS_REVIEW: 상수만 정의, MVP 미사용 (D-04)
```

### 2.3 MVP에서 실제로 강제하는 검증만 (D-04)

```python
# 강제 O
- STT 실행 전: audio.status in {AUDIO_RECEIVED, FAILED}   # DB명세 6.3
- PATCH 시:   structured.status != USER_CONFIRMED         # 아니면 AlreadyConfirmedError

# 강제 X (MVP는 관대하게 — 과설계 금지)
- 그 외 전이 순서 엄격 검증은 Phase 2
```

> 상태 전이를 함수로 캡슐화 권장:
```python
# app/services/_transitions.py (선택)
def ensure_audio_can_transcribe(audio):
    if audio.status not in (C.AUDIO_RECEIVED, C.FAILED):
        raise InvalidStatusTransitionError(
            f"현재 상태 {audio.status}에서는 STT를 실행할 수 없습니다.")
```

---

## 3. core 유틸 3종 (D-08 확정)

### 3.1 id_utils.py (D-10)

```python
# app/core/id_utils.py
import uuid
from app.core.time_utils import now

def new_id(prefix: str) -> str:
    ts = now().strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"{prefix}_{ts}_{short}"

# 편의 래퍼
def new_audio_id():      return new_id("audio")
def new_transcript_id(): return new_id("transcript")
def new_structured_id(): return new_id("structured")
def new_evidence_id():   return new_id("evidence")
def new_change_id():     return new_id("change")
```
- 예: `audio_20260703_153012_a1b2c3` (DB명세 2.1)

### 3.2 time_utils.py (D-07)

```python
# app/core/time_utils.py
from datetime import datetime

def now() -> datetime:
    # MVP: 서버 로컬. Phase2 UTC 전환 시 여기 1줄만 수정.
    return datetime.now()

def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None
```

### 3.3 json_utils.py (지시서 13.3, DB명세 2.3)

```python
# app/core/json_utils.py
import json

def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)

def loads(s: str | None):
    return json.loads(s) if s else None
```
- TEXT 컬럼 대상: `segments_json, ai_structured_json, user_confirmed_json, changed_fields_json, previous_value_json, new_value_json`

---

## 4. 레포지토리 패턴

### 4.1 공통 규약
- 생성자에서 `db: Session` 주입.
- **찾으면 모델 / 없으면 `None`** (404 판단은 서비스).
- 저장 시 `add → flush`(id 확보) → 서비스가 커밋 시점 제어(또는 세션 의존성이 커밋).

### 4.2 예시 (audio_repository)

```python
# app/repositories/audio_repository.py
from sqlalchemy.orm import Session
from app.models.audio_record import AudioRecord

class AudioRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **fields) -> AudioRecord:
        rec = AudioRecord(**fields)
        self.db.add(rec)
        self.db.flush()          # rec.id 확보
        return rec

    def get_by_audio_id(self, audio_id: str) -> AudioRecord | None:
        return (self.db.query(AudioRecord)
                .filter(AudioRecord.audio_id == audio_id).first())

    def update_status(self, rec: AudioRecord, status: str):
        rec.status = status
        rec.updated_at = now()   # D-01
        self.db.flush()
```

동일 패턴으로: `transcript_repository`, `structured_repository`, `evidence_repository`, `change_log_repository`.

---

## 5. 서비스 오케스트레이션 (대표 3종 의사코드)

### 5.1 stt_service.transcribe

```python
def transcribe(db, audio_id: str) -> dict:
    audio = audio_repo.get_by_audio_id(audio_id)
    if not audio:
        raise AudioNotFoundError()
    ensure_audio_can_transcribe(audio)          # §2.3

    try:
        result = mock_stt_provider.run(audio_id) # providers
    except Exception as e:
        audio_repo.update_status(audio, C.FAILED)
        raise SttError() from e

    transcript_id = new_transcript_id()
    transcript_repo.create(
        transcript_id=transcript_id, audio_id=audio_id,
        stt_provider=result["stt_provider"], language=result["language"],
        raw_transcript=result["raw_transcript"],
        cleaned_transcript=result["cleaned_transcript"],
        segments_json=json_utils.dumps(result["segments"]),
        confidence_avg=result["confidence_avg"],
        stt_status=result["stt_status"], created_at=now(),
    )
    audio_repo.update_status(audio, C.STT_COMPLETED)
    return {"ok": True, "audio_id": audio_id, "transcript_id": transcript_id,
            "stt_provider": result["stt_provider"], "stt_status": result["stt_status"]}
```

### 5.2 structure_service.run (CAREBASE_DESIGN §0 구현)

```python
def run(db, transcript_id: str, domain: str) -> dict:
    if domain not in C.ALLOWED_DOMAINS:
        raise InvalidDomainError()
    tr = transcript_repo.get_by_transcript_id(transcript_id)
    if not tr:
        raise TranscriptNotFoundError()

    segments = json_utils.loads(tr.segments_json) or []
    try:
        draft = extractor.extract(tr.cleaned_transcript, segments)
        draft = safety_rules.apply(draft)
        evidences = evidence_mapper.map(draft, segments)
    except Exception as e:
        raise StructureError() from e

    structured_id = new_structured_id()
    structured_repo.create(
        structured_id=structured_id, audio_id=tr.audio_id,
        transcript_id=transcript_id, domain=domain,
        schema_version=draft["schema_version"],
        ai_structured_json=json_utils.dumps(draft),
        user_confirmed_json=None, status=C.AI_TEMP, created_at=now(),
    )
    for ev in evidences:
        evidence_repo.create(evidence_id=new_evidence_id(),
                             structured_id=structured_id, created_at=now(), **ev)

    audio = audio_repo.get_by_audio_id(tr.audio_id)
    if audio:
        audio_repo.update_status(audio, C.STRUCTURED)

    return {"ok": True, "structured_id": structured_id, "status": C.AI_TEMP,
            "structured_json": draft, "evidence_count": len(evidences)}
```

### 5.3 structure_service.update (PATCH) — 병합 + ChangeLog

```python
def update(db, structured_id: str, changed_by: str, edited_fields: dict) -> dict:
    rec = structured_repo.get_by_structured_id(structured_id)
    if not rec:
        raise StructuredRecordNotFoundError()
    if rec.status == C.USER_CONFIRMED:
        raise AlreadyConfirmedError()                       # 409

    base = json_utils.loads(rec.user_confirmed_json) \
           or json_utils.loads(rec.ai_structured_json)      # DB명세 6.6 순서 4
    previous = {k: base.get(k) for k in edited_fields}      # 변경 전 값
    merged = {**base, **edited_fields}
    merged = safety_rules.apply(merged)                     # 수정에도 안전규칙(13.5)

    structured_repo.save_user_json(rec, json_utils.dumps(merged),
                                   status=C.USER_EDITED, updated_at=now())
    change_log_repo.create(
        change_id=new_change_id(), structured_id=structured_id,
        changed_fields_json=json_utils.dumps(list(edited_fields.keys())),
        previous_value_json=json_utils.dumps(previous),
        new_value_json=json_utils.dumps({k: merged.get(k) for k in edited_fields}),
        changed_by=changed_by, created_at=now(),
    )
    return {"ok": True, "structured_id": structured_id,
            "status": C.USER_EDITED, "changed_fields": list(edited_fields.keys())}
```

### 5.4 confirmation_service.confirm — 멱등 처리 (DB명세 6.7)

```python
def confirm(db, structured_id: str, confirmed_by: str) -> dict:
    rec = structured_repo.get_by_structured_id(structured_id)
    if not rec:
        raise StructuredRecordNotFoundError()

    if rec.status == C.USER_CONFIRMED:                      # 멱등 200
        return {"ok": True, "structured_id": structured_id,
                "status": C.USER_CONFIRMED, "message": "이미 확정된 기록입니다."}

    if not rec.user_confirmed_json:                         # 수정없이 확정 → AI본 복사
        rec.user_confirmed_json = rec.ai_structured_json
    rec.status = C.USER_CONFIRMED
    rec.confirmed_at = now()
    structured_repo.flush(rec)

    audio = audio_repo.get_by_audio_id(rec.audio_id)
    if audio:
        audio_repo.update_status(audio, C.CONFIRMED)
    # TODO(Phase2): UserConfirmationLog에 confirmed_by 기록 (D-06)
    return {"ok": True, "structured_id": structured_id,
            "status": C.USER_CONFIRMED, "confirmed_at": iso(rec.confirmed_at)}
```

---

## 6. DB 세션 & 의존성 주입

```python
# app/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

engine = create_engine("sqlite:///voicestruct_core.db",
                       connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

def get_db():                      # FastAPI Depends
    db = SessionLocal()
    try:
        yield db
        db.commit()                # 요청 성공 시 커밋
    except Exception:
        db.rollback()              # 예외 시 롤백 → 부분 저장 방지
        raise
    finally:
        db.close()

def init_db():                     # main.py 시작 시 테이블 생성
    import app.models  # 모든 모델 import (테이블 등록)
    Base.metadata.create_all(bind=engine)
```

> **트랜잭션 경계 = 요청 1개.** 서비스 안에서 여러 레코드를 `flush`만 하고, 성공하면 `get_db`가 한 번에 커밋 → 구조화 도중 실패 시 StructuredRecord/Evidence가 반쪽 저장되는 사고 방지.

---

## 7. main.py 조립

```python
# app/main.py
from fastapi import FastAPI
from app.core.database import init_db
from app.core.exceptions import register_exception_handlers
from app.api import audio_routes, stt_routes, structure_routes

app = FastAPI(title="VoiceStruct Core MVP", version="0.1.0")
register_exception_handlers(app)
app.include_router(audio_routes.router)
app.include_router(stt_routes.router)
app.include_router(structure_routes.router)

@app.on_event("startup")
def _startup():
    init_db()

@app.get("/")
def health():
    return {"ok": True, "service": "VoiceStruct Core MVP", "version": "0.1.0"}
```

---

## 8. 이 설계가 주는 것 (요약)

| 문제 | 이 설계의 해법 |
|------|----------------|
| 라우터마다 에러 처리 중복 | 도메인 예외 + 핸들러 1곳 (§1) |
| 404/409 판단이 여기저기 흩어짐 | 레포=None 반환 / 서비스=판단·예외 (§4,5) |
| 구조화 중간 실패 시 반쪽 저장 | 요청 단위 트랜잭션 커밋/롤백 (§6) |
| 상태 문자열 오타 | constants 상수 + 전이 헬퍼 (§2) |
| UTC 전환/ID 형식 산재 | core 유틸 3종에 격리 (§3) |
| 확정 후 수정/재확정 | 409 + 멱등 200 (§5.3, §5.4) |

→ **모든 API가 동일한 뼈대를 공유** → Slice 1~6이 "같은 패턴 복붙 + 도메인 로직만 교체"가 됨.

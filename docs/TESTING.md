# VoiceStruct Core — 테스트 전략 & 픽스처 상세 설계

> 대상: `tests/*`, `conftest.py`
> 기준: 개발 지시서 13장, DB-API 명세서 12장, ARCHITECTURE.md, CAREBASE_DESIGN.md
> 목적: MVP 완료 기준("pytest 전체 통과")을 실제 테스트 코드 수준으로 확정 → TDD 가능

---

## 0. 테스트 철학

| 원칙 | 내용 |
|------|------|
| **인메모리 DB** | 실제 `voicestruct_core.db` 건드리지 않음. `sqlite:///:memory:`로 격리 |
| **2층 구조** | ① 단위(도메인 순수함수) ② E2E(TestClient로 API 관통) |
| **결정적(deterministic)** | Mock STT 고정 출력 → 기대값 하드코딩 가능 |
| **격리** | 테스트마다 DB 초기화(픽스처). 순서 의존 금지 |
| **속도** | 외부 I/O 없음(파일은 tmp_path). 전체 1초 내 목표 |

**단위 vs E2E 나누는 기준**: extractor/safety/evidence 같은 **순수함수는 단위**로(빠르고 촘촘), 상태전이·DB·트랜잭션이 얽힌 건 **E2E**로.

---

## 1. conftest.py — 공용 픽스처

### 1.1 인메모리 DB + 의존성 오버라이드

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db

@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,          # 인메모리 DB를 커넥션 간 공유(중요)
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture()
def client(db_session):
    # get_db를 테스트 세션으로 교체 (요청 성공 시 커밋 흉내)
    def _override():
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

> **StaticPool 주의**: 인메모리 SQLite는 커넥션마다 별도 DB가 생기는 함정이 있음. `StaticPool + check_same_thread=False`로 단일 커넥션 공유해야 API가 만든 데이터를 검증에서 볼 수 있음.

### 1.2 파이프라인 헬퍼 픽스처 (E2E 체인 단축)

```python
# tests/conftest.py (이어서)
@pytest.fixture()
def uploaded_audio(client, tmp_path):
    f = tmp_path / "sample.wav"
    f.write_bytes(b"RIFF....fake wav")
    resp = client.post("/api/audio/upload",
        data={"user_id": "user_001", "domain": "carebase_memory"},
        files={"file": ("sample.wav", f.read_bytes(), "audio/wav")})
    return resp.json()["audio_id"]

@pytest.fixture()
def transcript_of(client, uploaded_audio):
    resp = client.post("/api/stt/transcribe", json={"audio_id": uploaded_audio})
    return resp.json()["transcript_id"]

@pytest.fixture()
def structured_of(client, transcript_of):
    resp = client.post("/api/structure/run",
        json={"transcript_id": transcript_of, "domain": "carebase_memory"})
    return resp.json()["structured_id"]
```

> 이렇게 체이닝하면 각 테스트가 `structured_of`만 받아도 "업로드→STT→구조화"가 끝난 상태에서 시작 → 수정/확정 테스트가 짧아짐.

---

## 2. 필수 테스트 14종 (DB명세 12.1) — 전체 설계

### 2.1 test_health_check

```python
def test_health_check(client):
    r = client.get("/")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["service"] == "VoiceStruct Core MVP"
    assert j["version"] == "0.1.0"
```

### 2.2 test_audio_upload_success

```python
def test_audio_upload_success(client, tmp_path):
    f = tmp_path / "sample.wav"; f.write_bytes(b"fakewav")
    r = client.post("/api/audio/upload",
        data={"user_id": "user_001", "domain": "carebase_memory"},
        files={"file": ("sample.wav", f.read_bytes(), "audio/wav")})
    assert r.status_code == 201
    j = r.json()
    assert j["ok"] is True
    assert j["audio_id"].startswith("audio_")
    assert j["status"] == "AUDIO_RECEIVED"
    assert j["file_path"].startswith("storage/audio/")
```

### 2.3 test_audio_upload_invalid_domain

```python
def test_audio_upload_invalid_domain(client, tmp_path):
    f = tmp_path / "x.wav"; f.write_bytes(b"x")
    r = client.post("/api/audio/upload",
        data={"user_id": "user_001", "domain": "meeting"},
        files={"file": ("x.wav", f.read_bytes(), "audio/wav")})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_DOMAIN"
```

### 2.4 test_mock_stt_success (기대값 DB명세 12.2)

```python
def test_mock_stt_success(client, uploaded_audio):
    r = client.post("/api/stt/transcribe", json={"audio_id": uploaded_audio})
    assert r.status_code == 201
    j = r.json()
    assert j["stt_provider"] == "mock_stt"
    assert j["stt_status"] == "SUCCESS"
    assert j["transcript_id"].startswith("transcript_")
    # 상세 조회로 내부 검증(선택): confidence_avg==0.9, segments>=3
```

### 2.5 test_mock_stt_audio_not_found

```python
def test_mock_stt_audio_not_found(client):
    r = client.post("/api/stt/transcribe", json={"audio_id": "audio_nope"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "AUDIO_NOT_FOUND"
```

### 2.6 test_structure_run_success (기대값 DB명세 12.2)

```python
def test_structure_run_success(client, transcript_of):
    r = client.post("/api/structure/run",
        json={"transcript_id": transcript_of, "domain": "carebase_memory"})
    assert r.status_code == 201
    j = r.json()
    assert j["status"] == "AI_TEMP"
    s = j["structured_json"]
    assert s["domain"] == "carebase_memory"
    assert s["schema_version"] == "carebase_memory_v1"
    assert "아버지" in s["people"]
    assert "병원" in s["places"]
    assert any(c["category"] == "TIME_CONFUSION" for c in s["risk_signal_candidates"])
    assert s["requires_user_confirmation"] is True
    assert j["evidence_count"] >= 3
```

### 2.7 test_structure_run_transcript_not_found

```python
def test_structure_run_transcript_not_found(client):
    r = client.post("/api/structure/run",
        json={"transcript_id": "transcript_nope", "domain": "carebase_memory"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "TRANSCRIPT_NOT_FOUND"
```

### 2.8 test_evidence_created (DB명세 12.2)

```python
def test_evidence_created(client, structured_of):
    r = client.get(f"/api/structure/{structured_of}/evidence")
    assert r.status_code == 200
    ev = r.json()["evidence"]
    assert len(ev) >= 3
    fields = {e["field_name"] for e in ev}
    assert "people" in fields
    assert "places" in fields
    assert "time_reference" in fields
    # 시간정보 존재 확인
    people_ev = next(e for e in ev if e["field_name"] == "people")
    assert people_ev["start_time"] is not None
```

### 2.9 test_structure_update_success

```python
def test_structure_update_success(client, structured_of):
    r = client.patch(f"/api/structure/{structured_of}",
        json={"changed_by": "user_001",
              "edited_fields": {"memory_summary": "수정본",
                                "time_reference": "어제 또는 오늘"}})
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "USER_EDITED"
    assert set(j["changed_fields"]) == {"memory_summary", "time_reference"}
    # user_confirmed_json 반영 확인
    g = client.get(f"/api/structure/{structured_of}").json()
    assert g["user_confirmed_json"]["memory_summary"] == "수정본"
```

### 2.10 test_change_log_created

```python
def test_change_log_created(client, structured_of):
    client.patch(f"/api/structure/{structured_of}",
        json={"changed_by": "user_001",
              "edited_fields": {"time_reference": "어제 또는 오늘"}})
    r = client.get(f"/api/structure/{structured_of}/changes")
    assert r.status_code == 200
    changes = r.json()["changes"]
    assert len(changes) >= 1
    c0 = changes[0]
    assert "time_reference" in c0["changed_fields"]
    assert c0["previous_value"]["time_reference"] == "오늘 또는 어제"
    assert c0["new_value"]["time_reference"] == "어제 또는 오늘"
    assert c0["changed_by"] == "user_001"
```

### 2.11 test_update_already_confirmed_rejected

```python
def test_update_already_confirmed_rejected(client, structured_of):
    client.post(f"/api/structure/{structured_of}/confirm",
                json={"confirmed_by": "user_001"})
    r = client.patch(f"/api/structure/{structured_of}",
        json={"changed_by": "user_001", "edited_fields": {"topic": "변경시도"}})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "ALREADY_CONFIRMED"
```

### 2.12 test_confirm_success (DB명세 12.2)

```python
def test_confirm_success(client, structured_of):
    r = client.post(f"/api/structure/{structured_of}/confirm",
                    json={"confirmed_by": "user_001"})
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "USER_CONFIRMED"
    assert j["confirmed_at"] is not None
    # AudioRecord.status == CONFIRMED 확인 (상세 조회로 audio_id → 재조회 or 직접 검증)
    g = client.get(f"/api/structure/{structured_of}").json()
    assert g["status"] == "USER_CONFIRMED"
    assert g["confirmed_at"] is not None
```

### 2.13 test_confirm_idempotent (DB명세 6.7)

```python
def test_confirm_idempotent(client, structured_of):
    client.post(f"/api/structure/{structured_of}/confirm", json={"confirmed_by": "u"})
    r = client.post(f"/api/structure/{structured_of}/confirm", json={"confirmed_by": "u"})
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "USER_CONFIRMED"
    assert j.get("message") == "이미 확정된 기록입니다."
```

### 2.14 test_safety_rules_no_forbidden_expression

```python
# 단위 테스트 (도메인 순수함수 직접 호출)
from app.domains.carebase import safety_rules
import json

def test_safety_rules_no_forbidden_expression():
    draft = {"memory_summary": "치매 의심 소견이 있다",
             "safety_notice": "이 결과는 진단이 아니라 사용자 자기기록 기반 참고 신호입니다."}
    out = safety_rules.apply(draft)
    blob = json.dumps(out, ensure_ascii=False)
    assert "치매 의심" not in blob                 # 금지 표현 제거
    assert "표현 변화 후보" in blob                 # 안전 표현 치환
    assert "진단이 아니라" in blob                  # 허용 문맥 보존
```

---

## 3. 추가 단위 테스트 (권장, 도메인 순수함수)

명세 필수는 아니지만 리팩터 안전망 + 규칙 정확도 보장.

```python
# tests/test_extractor.py
from app.domains.carebase import extractor
from app.providers import mock_stt_provider

def _mock_segments():
    return mock_stt_provider.run("audio_x")["segments"]

def test_extract_full_from_mock():
    r = mock_stt_provider.run("audio_x")
    d = extractor.extract(r["cleaned_transcript"], r["segments"])
    assert d["people"] == ["아버지"]
    assert d["places"] == ["병원"]
    assert d["time_reference"] == "오늘 또는 어제"
    assert d["emotion"] == ["안도"]
    assert d["missing_fields"] == []
    assert d["requires_user_confirmation"] is True

def test_extract_empty_text_marks_missing():
    d = extractor.extract("아무 내용 없음", [])
    assert "people" in d["missing_fields"]
    assert "places" in d["missing_fields"]

# tests/test_evidence_mapper.py
from app.domains.carebase import evidence_mapper, extractor

def test_evidence_time_ranges():
    r = mock_stt_provider.run("audio_x")
    d = extractor.extract(r["cleaned_transcript"], r["segments"])
    evs = evidence_mapper.map(d, r["segments"])
    people_ev = next(e for e in evs if e["field_name"] == "people")
    assert people_ev["start_time"] == 0.0 and people_ev["end_time"] == 4.2
    tr_ev = next(e for e in evs if e["field_name"] == "time_reference")
    assert tr_ev["start_time"] == 4.3
```

---

## 4. 테스트 매트릭스 (커버리지 확인표)

| 테스트 | 계층 | 검증 대상 | Slice |
|--------|------|-----------|-------|
| test_health_check | E2E | 서버 기동 | S0 |
| test_audio_upload_success | E2E | 업로드+201 | S1 |
| test_audio_upload_invalid_domain | E2E | 400 도메인 | S1 |
| test_mock_stt_success | E2E | STT+상태전이 | S2 |
| test_mock_stt_audio_not_found | E2E | 404 | S2 |
| test_structure_run_success | E2E | 구조화 기대값 | S3 |
| test_structure_run_transcript_not_found | E2E | 404 | S3 |
| test_evidence_created | E2E | evidence≥3 | S3 |
| test_safety_rules_* | 단위 | 금지표현 치환 | S3 |
| test_extract_* (권장) | 단위 | 추출 규칙 | S3 |
| test_structure_update_success | E2E | 병합+USER_EDITED | S5 |
| test_change_log_created | E2E | ChangeLog | S5 |
| test_update_already_confirmed_rejected | E2E | 409 | S6 |
| test_confirm_success | E2E | 확정+상태전이 | S6 |
| test_confirm_idempotent | E2E | 멱등 200 | S6 |

→ **모든 슬라이스가 테스트로 커버됨.** 슬라이스 구현 = 해당 테스트 green.

---

## 5. 실행 & CI

### 5.1 로컬 실행
```bash
pytest                      # 전체
pytest -v                   # 상세
pytest tests/test_confirmation_flow.py::test_confirm_idempotent   # 단건
pytest --cov=app            # 커버리지(선택, pytest-cov)
```

### 5.2 파일 배치 (지시서 13.1 + 권장 추가)
```
tests/
  conftest.py                     # 픽스처 (§1)
  test_audio_upload.py            # 2.2, 2.3
  test_mock_stt.py                # 2.4, 2.5
  test_carebase_structure.py      # 2.6, 2.7, 2.14
  test_confirmation_flow.py       # 2.9~2.13
  test_health.py                  # 2.1 (권장 분리)
  test_evidence.py                # 2.8 (권장 분리)
  test_extractor.py               # §3 (권장)
  test_evidence_mapper.py         # §3 (권장)
```

### 5.3 Phase 2 CI (GitHub Actions 방향)
```yaml
# .github/workflows/ci.yml (Phase 2)
- ruff check app tests          # 린트
- pytest --cov=app --cov-fail-under=80
```
- **안전 규칙 테스트를 필수 게이트로**: `test_safety_rules_*` 실패 시 머지 차단 (헬스 인접 도메인 리스크).

---

## 6. 흔한 함정 체크리스트

- [ ] 인메모리 DB에 **StaticPool** 안 쓰면 "테이블 없음/데이터 안 보임" 에러 → §1.1
- [ ] `dependency_overrides`로 `get_db` 교체 안 하면 실제 파일 DB 오염
- [ ] Mock STT가 랜덤/시간 의존이면 기대값 하드코딩 불가 → **고정 출력** 유지(D-09 근거)
- [ ] 파일 업로드 테스트는 실제 wav 불필요 → 더미 바이트 + tmp_path
- [ ] confirm 후 audio 상태 검증하려면 조회 경로 확보(구조화 조회에 audio_id 포함되므로 재조회 가능)
- [ ] 테스트 간 DB 격리(픽스처 teardown에서 drop_all)로 순서 의존 제거
```

# VoiceStruct Core MVP

음성 정보를 목적별 구조화 데이터로 변환하는 공통 엔진. 이번 MVP는
**CareBase Memory 단일 도메인** 파이프라인을 로컬에서 동작시킨다.

> 파이프라인: 음성 업로드 → Mock STT → Transcript → CareBase 구조화(AI_TEMP)
> → 원문 근거(Evidence) 연결 → 사용자 수정 → 사용자 확정 → Change Log

설계 문서는 `docs/` 참고: `ROADMAP` / `DECISIONS` / `CAREBASE_DESIGN` /
`ARCHITECTURE` / `TESTING` / `PHASE2_ENGINE`.

## 1. 기술 스택
Python 3.11+ · FastAPI · Uvicorn · SQLAlchemy · SQLite · Pydantic · pytest

## 2. 로컬 실행

### macOS / Linux
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Windows PowerShell
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

서버: http://127.0.0.1:8000  ·  문서(Swagger): http://127.0.0.1:8000/docs

## 3. API 테스트 예시

```bash
# Health
curl http://127.0.0.1:8000/

# 1) 음성 업로드
curl -X POST "http://127.0.0.1:8000/api/audio/upload" \
  -F "user_id=user_001" -F "domain=carebase_memory" -F "file=@sample.wav"

# 2) Mock STT (위에서 받은 audio_id 사용)
curl -X POST "http://127.0.0.1:8000/api/stt/transcribe" \
  -H "Content-Type: application/json" -d '{"audio_id":"<audio_id>"}'

# 3) 구조화 실행 (위에서 받은 transcript_id 사용)
curl -X POST "http://127.0.0.1:8000/api/structure/run" \
  -H "Content-Type: application/json" \
  -d '{"transcript_id":"<transcript_id>","domain":"carebase_memory"}'

# 4) 상세 조회 / 원문 근거 / 수정 이력
curl http://127.0.0.1:8000/api/structure/<structured_id>
curl http://127.0.0.1:8000/api/structure/<structured_id>/evidence
curl http://127.0.0.1:8000/api/structure/<structured_id>/changes

# 5) 수정
curl -X PATCH "http://127.0.0.1:8000/api/structure/<structured_id>" \
  -H "Content-Type: application/json" \
  -d '{"changed_by":"user_001","edited_fields":{"time_reference":"어제 또는 오늘"}}'

# 6) 확정
curl -X POST "http://127.0.0.1:8000/api/structure/<structured_id>/confirm" \
  -H "Content-Type: application/json" -d '{"confirmed_by":"user_001"}'
```

## 4. 테스트

```bash
pytest          # 전체
pytest -v       # 상세
```

## 5. MVP 제외 범위
실제 STT(CLOVA/RTZR/Google), 실제 LLM 구조화, 프론트엔드, 로그인/보호자 권한,
119 응급 모듈, 회의록/상담 모듈, 클라우드 배포, 실시간 스트리밍, 의료 진단·예측.
→ 이후 확장 방향은 `docs/PHASE2_ENGINE.md`, `docs/DEVELOPMENT_ROADMAP.md` 참고.

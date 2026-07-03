"""공용 픽스처 (TESTING.md §1). 인메모리 SQLite + get_db 오버라이드."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 인메모리 DB를 커넥션 간 공유 (필수)
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


# ── 파이프라인 헬퍼 픽스처 ──
@pytest.fixture()
def uploaded_audio(client, tmp_path):
    f = tmp_path / "sample.wav"
    f.write_bytes(b"RIFF....fake wav")
    resp = client.post(
        "/api/audio/upload",
        data={"user_id": "user_001", "domain": "carebase_memory"},
        files={"file": ("sample.wav", f.read_bytes(), "audio/wav")},
    )
    return resp.json()["audio_id"]


@pytest.fixture()
def transcript_of(client, uploaded_audio):
    resp = client.post("/api/stt/transcribe", json={"audio_id": uploaded_audio})
    return resp.json()["transcript_id"]


@pytest.fixture()
def structured_of(client, transcript_of):
    resp = client.post(
        "/api/structure/run",
        json={"transcript_id": transcript_of, "domain": "carebase_memory"},
    )
    return resp.json()["structured_id"]

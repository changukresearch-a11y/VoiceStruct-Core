"""SQLite 연결 + 세션 (ARCHITECTURE §6).

트랜잭션 경계 = 요청 1개. 요청 성공 시 커밋, 예외 시 롤백 → 반쪽 저장 방지.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    """FastAPI Depends용 세션. 요청 성공 시 커밋, 예외 시 롤백."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """모든 모델을 import 하여 테이블을 생성한다."""
    import app.models  # noqa: F401  (모델 등록)

    Base.metadata.create_all(bind=engine)

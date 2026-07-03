"""시간 유틸 (DECISIONS D-07).

MVP는 서버 로컬 시간을 쓰되, 모든 시각 생성은 now() 한 곳만 경유한다.
추후 UTC 전환은 이 함수 1개 수정으로 끝난다.
"""

from datetime import datetime


def now() -> datetime:
    # NOTE(Phase2): UTC 전환 시 여기 1줄만 datetime.utcnow()로 교체
    return datetime.now()


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None

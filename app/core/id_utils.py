"""외부 API용 문자열 ID 생성 (DECISIONS D-10, DB명세 2.1).

형식: {prefix}_{YYYYMMDD_HHMMSS}_{short_uuid}
예)   audio_20260703_153012_a1b2c3
"""

import uuid

from app.core.time_utils import now


def new_id(prefix: str) -> str:
    ts = now().strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"{prefix}_{ts}_{short}"


def new_audio_id() -> str:
    return new_id("audio")


def new_transcript_id() -> str:
    return new_id("transcript")


def new_structured_id() -> str:
    return new_id("structured")


def new_evidence_id() -> str:
    return new_id("evidence")


def new_change_id() -> str:
    return new_id("change")

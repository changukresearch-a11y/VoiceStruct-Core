"""JSON 저장/복원 유틸 (지시서 13.3, DB명세 2.3).

TEXT 컬럼에 JSON 문자열로 저장하는 필드가 많으므로 dumps/loads를 여기 모은다.
대상: segments_json, ai_structured_json, user_confirmed_json,
      changed_fields_json, previous_value_json, new_value_json
"""

import json
from typing import Any


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def loads(s: str | None) -> Any:
    return json.loads(s) if s else None

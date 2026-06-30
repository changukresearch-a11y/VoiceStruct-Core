"""
Form 유형 라우터.

공시 Form 종류마다 코드/LLM 비중이 다르다(메모리 disclosure-pipeline 핵심).
어떤 처리 경로를 탈지 여기서 결정한다.

- 8-K   : Item 라우터(코드) + 해당 Item 본문만 LLM
- 10-Q/K: 숫자=XBRL(코드), LLM은 가이던스 뉘앙스만
- 4     : XML 파싱 100% 코드, LLM 배제
- S-1/424B: 희석 계산(코드) + 자금용도 LLM
"""
from __future__ import annotations

from typing import Any

FORM_HANDLERS: dict[str, dict[str, Any]] = {
    "8-K":   {"needs_item_router": True,  "needs_xbrl": False, "needs_form4": False, "needs_llm": True},
    "10-Q":  {"needs_item_router": False, "needs_xbrl": True,  "needs_form4": False, "needs_llm": True},
    "10-K":  {"needs_item_router": False, "needs_xbrl": True,  "needs_form4": False, "needs_llm": True},
    "4":     {"needs_item_router": False, "needs_xbrl": False, "needs_form4": True,  "needs_llm": False},
    "S-1":   {"needs_item_router": False, "needs_xbrl": False, "needs_form4": False, "needs_llm": True},
    "424B":  {"needs_item_router": False, "needs_xbrl": False, "needs_form4": False, "needs_llm": True},
}

_DEFAULT = {"needs_item_router": False, "needs_xbrl": False, "needs_form4": False, "needs_llm": True}


def route_form(form_type: str) -> dict[str, Any]:
    """form_type → 처리 경로 플래그. 매핑에 없으면 LLM만."""
    return {"form_type": form_type, **FORM_HANDLERS.get(form_type, _DEFAULT)}

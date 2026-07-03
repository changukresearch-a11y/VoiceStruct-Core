import json

from app.domains.carebase import safety_rules


def test_structure_run_success(client, transcript_of):
    r = client.post(
        "/api/structure/run",
        json={"transcript_id": transcript_of, "domain": "carebase_memory"},
    )
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


def test_structure_run_transcript_not_found(client):
    r = client.post(
        "/api/structure/run",
        json={"transcript_id": "transcript_nope", "domain": "carebase_memory"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "TRANSCRIPT_NOT_FOUND"


def test_safety_rules_no_forbidden_expression():
    draft = {
        "memory_summary": "치매 의심 소견이 있다",
        "safety_notice": "이 결과는 진단이 아니라 사용자 자기기록 기반 참고 신호입니다.",
    }
    out = safety_rules.apply(draft)
    blob = json.dumps(out, ensure_ascii=False)
    assert "치매 의심" not in blob
    assert "표현 변화 후보" in blob
    assert "진단이 아니라" in blob

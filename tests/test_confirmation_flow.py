from app.models.audio_record import AudioRecord


def test_structure_update_success(client, structured_of):
    r = client.patch(
        f"/api/structure/{structured_of}",
        json={
            "changed_by": "user_001",
            "edited_fields": {
                "memory_summary": "수정본",
                "time_reference": "어제 또는 오늘",
            },
        },
    )
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "USER_EDITED"
    assert set(j["changed_fields"]) == {"memory_summary", "time_reference"}

    g = client.get(f"/api/structure/{structured_of}").json()
    assert g["user_confirmed_json"]["memory_summary"] == "수정본"


def test_change_log_created(client, structured_of):
    client.patch(
        f"/api/structure/{structured_of}",
        json={"changed_by": "user_001", "edited_fields": {"time_reference": "어제 또는 오늘"}},
    )
    r = client.get(f"/api/structure/{structured_of}/changes")
    assert r.status_code == 200
    changes = r.json()["changes"]
    assert len(changes) >= 1
    c0 = changes[0]
    assert "time_reference" in c0["changed_fields"]
    assert c0["previous_value"]["time_reference"] == "오늘 또는 어제"
    assert c0["new_value"]["time_reference"] == "어제 또는 오늘"
    assert c0["changed_by"] == "user_001"


def test_update_already_confirmed_rejected(client, structured_of):
    client.post(f"/api/structure/{structured_of}/confirm", json={"confirmed_by": "user_001"})
    r = client.patch(
        f"/api/structure/{structured_of}",
        json={"changed_by": "user_001", "edited_fields": {"topic": "변경시도"}},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "ALREADY_CONFIRMED"


def test_confirm_success(client, structured_of, db_session):
    r = client.post(f"/api/structure/{structured_of}/confirm", json={"confirmed_by": "user_001"})
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "USER_CONFIRMED"
    assert j["confirmed_at"] is not None

    g = client.get(f"/api/structure/{structured_of}").json()
    assert g["status"] == "USER_CONFIRMED"
    assert g["confirmed_at"] is not None

    # 연결된 AudioRecord가 CONFIRMED로 전이됐는지 (DB명세 12.2)
    audio = (
        db_session.query(AudioRecord)
        .filter(AudioRecord.audio_id == g["audio_id"])
        .first()
    )
    assert audio.status == "CONFIRMED"


def test_confirm_idempotent(client, structured_of):
    client.post(f"/api/structure/{structured_of}/confirm", json={"confirmed_by": "u"})
    r = client.post(f"/api/structure/{structured_of}/confirm", json={"confirmed_by": "u"})
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "USER_CONFIRMED"
    assert j.get("message") == "이미 확정된 기록입니다."

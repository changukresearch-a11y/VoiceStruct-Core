def test_mock_stt_success(client, uploaded_audio):
    r = client.post("/api/stt/transcribe", json={"audio_id": uploaded_audio})
    assert r.status_code == 201
    j = r.json()
    assert j["stt_provider"] == "mock_stt"
    assert j["stt_status"] == "SUCCESS"
    assert j["transcript_id"].startswith("transcript_")


def test_mock_stt_audio_not_found(client):
    r = client.post("/api/stt/transcribe", json={"audio_id": "audio_nope"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "AUDIO_NOT_FOUND"

def test_audio_upload_success(client, tmp_path):
    f = tmp_path / "sample.wav"
    f.write_bytes(b"fakewav")
    r = client.post(
        "/api/audio/upload",
        data={"user_id": "user_001", "domain": "carebase_memory"},
        files={"file": ("sample.wav", f.read_bytes(), "audio/wav")},
    )
    assert r.status_code == 201
    j = r.json()
    assert j["ok"] is True
    assert j["audio_id"].startswith("audio_")
    assert j["status"] == "AUDIO_RECEIVED"
    assert j["file_path"].startswith("storage/audio/")


def test_audio_upload_invalid_domain(client, tmp_path):
    f = tmp_path / "x.wav"
    f.write_bytes(b"x")
    r = client.post(
        "/api/audio/upload",
        data={"user_id": "user_001", "domain": "meeting"},
        files={"file": ("x.wav", f.read_bytes(), "audio/wav")},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_DOMAIN"

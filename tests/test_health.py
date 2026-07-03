def test_health_check(client):
    r = client.get("/")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["service"] == "VoiceStruct Core MVP"
    assert j["version"] == "0.1.0"

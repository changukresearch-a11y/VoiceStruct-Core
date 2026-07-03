def test_evidence_created(client, structured_of):
    r = client.get(f"/api/structure/{structured_of}/evidence")
    assert r.status_code == 200
    ev = r.json()["evidence"]
    assert len(ev) >= 3
    fields = {e["field_name"] for e in ev}
    assert "people" in fields
    assert "places" in fields
    assert "time_reference" in fields
    people_ev = next(e for e in ev if e["field_name"] == "people")
    assert people_ev["start_time"] is not None

from app.domains.carebase import evidence_mapper, extractor
from app.providers import mock_stt_provider


def test_evidence_time_ranges():
    r = mock_stt_provider.run("audio_x")
    d = extractor.extract(r["cleaned_transcript"], r["segments"])
    evs = evidence_mapper.map(d, r["segments"])

    people_ev = next(e for e in evs if e["field_name"] == "people")
    assert people_ev["start_time"] == 0.0
    assert people_ev["end_time"] == 4.2

    tr_ev = next(e for e in evs if e["field_name"] == "time_reference")
    assert tr_ev["start_time"] == 4.3

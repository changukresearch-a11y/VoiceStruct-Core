from app.domains.carebase import extractor
from app.providers.mock_stt_provider import MockSttProvider


def test_extract_full_from_mock():
    r = MockSttProvider().transcribe("dummy.wav")
    d = extractor.extract(r.cleaned_transcript, r.segments)
    assert d["people"] == ["아버지"]
    assert d["places"] == ["병원"]
    assert d["time_reference"] == "오늘 또는 어제"
    assert d["emotion"] == ["안도"]
    assert d["missing_fields"] == []
    assert d["requires_user_confirmation"] is True


def test_extract_empty_text_marks_missing():
    d = extractor.extract("아무 내용 없음", [])
    assert "people" in d["missing_fields"]
    assert "places" in d["missing_fields"]

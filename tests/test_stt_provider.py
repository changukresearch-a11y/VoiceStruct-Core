"""STT Provider 계약 테스트 (PHASE2_ENGINE §1).

어떤 Provider 구현이든 이 계약을 지켜야 파이프라인이 동작한다.
"""

import pytest

from app.core.config import settings
from app.providers.base import SttProvider, TranscriptResult
from app.providers.mock_stt_provider import MockSttProvider
from app.providers.registry import get_stt_provider

_SEGMENT_KEYS = {"start_time", "end_time", "speaker", "text", "confidence"}


def _assert_valid_result(r: TranscriptResult):
    assert isinstance(r, TranscriptResult)
    assert r.stt_status == "SUCCESS"
    assert r.language == "ko-KR"
    assert isinstance(r.raw_transcript, str) and r.raw_transcript
    assert isinstance(r.cleaned_transcript, str) and r.cleaned_transcript
    assert len(r.segments) >= 3
    for s in r.segments:
        assert _SEGMENT_KEYS <= set(s)


def test_mock_provider_satisfies_contract():
    provider = MockSttProvider()
    # runtime_checkable Protocol 만족 확인
    assert isinstance(provider, SttProvider)
    r = provider.transcribe("dummy.wav")
    _assert_valid_result(r)
    assert r.stt_provider == "mock_stt"
    assert r.confidence_avg == 0.9
    assert r.duration_sec == 13.0


def test_registry_returns_mock_by_default():
    provider = get_stt_provider()
    assert provider.name == "mock_stt"
    _assert_valid_result(provider.transcribe("dummy.wav"))


def test_registry_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(settings, "stt_provider", "nonexistent")
    with pytest.raises(ValueError):
        get_stt_provider()

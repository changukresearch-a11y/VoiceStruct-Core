"""STT Provider 레지스트리 (PHASE2_ENGINE §1.2).

settings.stt_provider(환경변수 STT_PROVIDER) 값으로 Provider를 선택한다.
코드 변경 없이 환경변수 한 줄로 Mock ↔ 실제 Provider 전환.
"""

from app.core.config import settings
from app.providers.base import SttProvider
from app.providers.mock_stt_provider import MockSttProvider


def get_stt_provider() -> SttProvider:
    name = settings.stt_provider
    if name == "mock":
        return MockSttProvider()
    # NOTE(Phase2): 실제 Provider 추가 지점
    #   "clova":  return ClovaSttProvider(settings.clova_api_key)
    #   "rtzr":   return RtzrSttProvider(settings.rtzr_api_key)
    #   "google": return GoogleSttProvider(settings.google_credentials)
    raise ValueError(f"지원하지 않는 STT_PROVIDER 설정: {name!r}")

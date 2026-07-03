"""애플리케이션 설정."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "VoiceStruct Core MVP"
    version: str = "0.1.0"

    database_url: str = "sqlite:///voicestruct_core.db"
    audio_storage_dir: str = "storage/audio"

    # NOTE(Phase2): STT_PROVIDER, USE_LLM_EXTRACTOR 등 확장
    stt_provider: str = "mock"

    class Config:
        env_file = ".env"


settings = Settings()

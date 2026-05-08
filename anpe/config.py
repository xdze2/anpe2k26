from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    mistral_api_key: str
    mistral_model: str = "mistral-small-latest"
    mistral_base_url: str = "https://api.mistral.ai/v1"

    user_data_dir: Path = Path("user_vault")


settings = Settings()  # type: ignore[call-arg]

USER_DATA_DIR: Path = settings.user_data_dir

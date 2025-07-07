from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Mendefinisikan env variables yang dibutuhkan dan Pydantic otomatis memuat nilai dari file .env
    """
    # Environment variables
    ETHERSCAN_API_KEY: str
    GEMINI_API_KEY: str

    # Konfigurasi Docker
    SLITHER_DOCKER_IMAGE: str = "trailofbits/slither:latest"
    MYTHRIL_DOCKER_IMAGE: str = "/mythril/myth:latest"

    # Batasi waktu untuk analisis
    MYTHRIL_TIMEOUT_SECONDS: int = 720 # 12 menit
    LLM_TIMEOUT_SECONDS: int = 300 # 5 menit
    ETHERSCAN_TIMEOUT_SECONDS: int = 60 # 1 menit

    model_config = SettingsConfigDict(env_file = ".env", env_file_encoding="utf-8")

settings = Settings()
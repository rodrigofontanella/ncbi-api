# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    ncbi_api_key: str = ""
    ncbi_base_url: str = "https://api.ncbi.nlm.nih.gov/datasets/v2"
    database_url: str = "postgresql+asyncpg://ncbi_user:ncbi_pass@localhost:5432/ncbi_db"

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
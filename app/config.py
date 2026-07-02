from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ncbi_api_key: str = ""
    ncbi_base_url: str = "https://api.ncbi.nlm.nih.gov/datasets/v2"

    class Config:
        env_file = ".env"

settings = Settings()
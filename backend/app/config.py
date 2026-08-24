from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./callradar.db"
    media_root: Path = Path("./data")
    cors_origins: str = "http://localhost:3000"
    model_config = {"env_file": ".env"}

settings = Settings()

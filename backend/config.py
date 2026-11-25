import os
from typing import List
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
    LLM_API_KEYS: str = os.getenv("LLM_API_KEYS", "")
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    ENABLE_FAILURE_SIMULATION: bool = os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() in ("true", "1", "yes")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini/gemini-3.5-flash-lite")
    DEFAULT_SYSTEM_PROMPT: str = os.getenv("DEFAULT_SYSTEM_PROMPT", "You are a helpful and concise AI assistant.")

    @property
    def key_pool(self) -> List[str]:
        keys = [k.strip() for k in self.LLM_API_KEYS.split(",") if k.strip()]
        return keys

    @property
    def cors_origins(self) -> List[str]:
        origins = [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]
        return origins

settings = Settings()

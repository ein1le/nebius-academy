import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    openai_api_key: str
    openai_model: str
    max_total_chars: int
    max_chars_per_file: int


@lru_cache()
def get_settings() -> Settings:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    return Settings(
        openai_api_key=api_key,
        openai_model=model,
        max_total_chars=60000,
        max_chars_per_file=8000,
    )

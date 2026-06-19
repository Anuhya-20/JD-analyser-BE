from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "JD Analyser API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/jd_analyser"
    DATABASE_SYNC_URL: str = "postgresql://postgres:password@localhost:5432/jd_analyser"

    # AI Provider
    AI_PROVIDER: str = "groq"  # "groq" | "openai" | "google" | "deepseek"

    # Groq (free tier, OpenAI-compatible)
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Google Gemini
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_MODEL: str = "gemini-2.0-flash"

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"

    # DeepSeek
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # Embeddings
    EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
    EMBEDDING_DEVICE: str = "cpu"
    EMBEDDING_DIMENSION: int = 768

    # Auth / JWT
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8   # 8 hours
    RESET_TOKEN_EXPIRE_HOURS: int = 1
    OTP_EXPIRE_MINUTES: int = 10

    # Email / SMTP
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = ""
    EMAIL_FROM_NAME: str = "JD Analyser"

    # Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 50

    # Processing
    BATCH_SIZE: int = 10
    MAX_RESUME_PROCESSING_WORKERS: int = 20

    # Minimum overall score (0-100) a candidate must reach to receive LLM enrichment.
    # Set to 0.0 to give ALL candidates full strengths/weaknesses analysis.
    SCORE_MIN_FOR_LLM_ANALYSIS: float = 0.0

    # Scoring Weights — experienced candidates (must sum to 1.0)
    SCORE_WEIGHT_SKILL: float = 0.70
    SCORE_WEIGHT_EXPERIENCE: float = 0.10
    SCORE_WEIGHT_EDUCATION: float = 0.10
    SCORE_WEIGHT_SEMANTIC: float = 0.10

    # Scoring Weights — fresher on entry-level JD (must sum to 1.0)
    SCORE_WEIGHT_SKILL_FRESHER: float = 0.70
    SCORE_WEIGHT_EXPERIENCE_FRESHER: float = 0.05
    SCORE_WEIGHT_EDUCATION_FRESHER: float = 0.15
    SCORE_WEIGHT_SEMANTIC_FRESHER: float = 0.10

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

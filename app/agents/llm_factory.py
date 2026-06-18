"""
Factory for creating LLM instances.
Supports: deepseek | openai | google

Each agent passes max_tokens to cap output and avoid runaway responses.
DeepSeek pricing (V3): input $0.27/M | output $1.10/M tokens
"""
from functools import lru_cache
from langchain_core.language_models import BaseChatModel
from app.config import settings
from loguru import logger


@lru_cache(maxsize=16)
def get_llm(temperature: float = 0.1, max_tokens: int = 1024) -> BaseChatModel:
    """Return the configured LLM with an output token cap."""
    if settings.AI_PROVIDER == "deepseek":
        return _get_deepseek_llm(temperature, max_tokens)
    if settings.AI_PROVIDER == "google":
        return _get_google_llm(temperature, max_tokens)
    return _get_openai_llm(temperature, max_tokens)


def _get_deepseek_llm(temperature: float, max_tokens: int) -> BaseChatModel:
    if not settings.DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY is not set in environment")
    from langchain_openai import ChatOpenAI
    logger.debug(f"DeepSeek {settings.DEEPSEEK_MODEL} | temp={temperature} max_tokens={max_tokens}")
    return ChatOpenAI(
        model=settings.DEEPSEEK_MODEL,
        temperature=temperature,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        max_tokens=max_tokens,
        max_retries=3,
    )


def _get_openai_llm(temperature: float, max_tokens: int) -> BaseChatModel:
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not set in environment")
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=settings.OPENAI_MODEL,
        temperature=temperature,
        api_key=settings.OPENAI_API_KEY,
        max_tokens=max_tokens,
        max_retries=3,
    )


def _get_google_llm(temperature: float, max_tokens: int) -> BaseChatModel:
    if not settings.GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY is not set in environment")
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=settings.GOOGLE_MODEL,
        temperature=temperature,
        google_api_key=settings.GOOGLE_API_KEY,
        max_output_tokens=max_tokens,
    )

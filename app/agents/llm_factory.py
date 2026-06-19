"""
LLM Factory — returns a LangChain-compatible chat model.
Supports: groq | openai | google | deepseek
"""
from __future__ import annotations
from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from loguru import logger

from app.config import settings


@lru_cache(maxsize=16)
def get_llm(temperature: float = 0.1, max_tokens: int = 1024, provider: str = "") -> BaseChatModel:
    """Return the configured LLM with an output token cap."""
    _provider = (provider or settings.AI_PROVIDER).strip("\"' ").lower()
    logger.debug(f"[LLM] provider={_provider} temp={temperature} max_tokens={max_tokens}")

    if _provider == "groq":
        return _get_groq_llm(temperature, max_tokens)
    if _provider == "google":
        return _get_google_llm(temperature, max_tokens)
    if _provider == "deepseek":
        return _get_deepseek_llm(temperature, max_tokens)
    if _provider == "openai":
        return _get_openai_llm(temperature, max_tokens)

    raise ValueError(
        f"Unsupported AI_PROVIDER: '{_provider}'. Set to groq | openai | google | deepseek."
    )


def _get_groq_llm(temperature: float, max_tokens: int) -> BaseChatModel:
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set in environment")
    from langchain_openai import ChatOpenAI
    logger.debug(f"Groq {settings.GROQ_MODEL} | temp={temperature} max_tokens={max_tokens}")
    return ChatOpenAI(
        model=settings.GROQ_MODEL,
        temperature=temperature,
        api_key=settings.GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
        max_tokens=max_tokens,
        max_retries=3,
    )


def _get_google_llm(temperature: float, max_tokens: int) -> BaseChatModel:
    if not settings.GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY is not set in environment")
    from langchain_google_genai import ChatGoogleGenerativeAI
    logger.debug(f"Google Gemini {settings.GOOGLE_MODEL} | temp={temperature} max_tokens={max_tokens}")
    return ChatGoogleGenerativeAI(
        model=settings.GOOGLE_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )


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

"""LLM provider selection, env loading, timeouts and retries.

Every model call in the project goes through `invoke_agent`, which applies a
15-second timeout (set on the client itself) plus one retry with exponential
backoff, and converts any provider failure into `ProviderUnavailable` so the
API can answer 503 instead of leaking a traceback.
"""

import os
import time
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_community.chat_models import ChatZhipuAI
from pydantic import SecretStr

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load only this project's .env. A bare load_dotenv() walks up parent
# directories and would silently pick up an unrelated project's keys.
load_dotenv(PROJECT_ROOT / ".env")

REQUEST_TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 2
BACKOFF_BASE_SECONDS = 0.5

# Models per provider, kept in one place so /health and the clients agree.
MODELS = {
    "groq": "openai/gpt-oss-120b",
    "glm": "glm-4.7-flash",
    "gemini": "gemini-3-flash-preview",
}

SUPPORTED_PROVIDERS = tuple(MODELS)


class ProviderUnavailable(RuntimeError):
    """The model provider failed or is not configured. Maps to HTTP 503."""


class ProviderNotConfigured(ProviderUnavailable):
    """A required API key is missing. Maps to HTTP 503."""


def _require_env(*var_names: str) -> str:
    """Return the first non-empty value among `var_names`."""
    for name in var_names:
        value = os.getenv(name)
        if value:
            return value
    raise ProviderNotConfigured(f"{' or '.join(var_names)} not set")


def get_default_provider() -> str:
    """Return the configured provider name (default "groq")."""
    provider = (os.getenv("LLM_PROVIDER") or "groq").strip().lower()
    if provider not in MODELS:
        raise ProviderNotConfigured(f"Unknown LLM_PROVIDER {provider!r}; expected one of {', '.join(SUPPORTED_PROVIDERS)}")
    return provider


@lru_cache(maxsize=8)
def _get_llm_cached(provider: str):
    """Create and cache an LLM client for a given provider."""
    if provider == "groq":
        return ChatGroq(
            model=MODELS["groq"],
            api_key=SecretStr(_require_env("GROQ_API_KEY")),
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_retries=0,  # retries are handled by invoke_agent
        )
    if provider == "glm":
        return ChatZhipuAI(
            model=MODELS["glm"],
            api_key=_require_env("GLM_API_KEY"),
            request_timeout=REQUEST_TIMEOUT_SECONDS,
        )
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=MODELS["gemini"],
            api_key=_require_env("GEMINI_API_KEY", "GOOGLE_API_KEY"),
            request_timeout=REQUEST_TIMEOUT_SECONDS,
        )

    raise ProviderNotConfigured(f"Unknown provider: {provider}")


def get_llm(provider: str | None = None):
    """Return a shared LLM client, honouring the LLM_PROVIDER env var."""
    return _get_llm_cached(provider or get_default_provider())


def invoke_agent(agent, payload, *, attempts: int = MAX_ATTEMPTS):
    """Invoke a LangChain agent with timeout + exponential-backoff retry.

    Raises ProviderUnavailable once every attempt has failed.
    """
    last_error: Exception | None = None

    for attempt in range(attempts):
        if attempt:
            time.sleep(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
        try:
            return agent.invoke(payload)
        except Exception as exc:  # noqa: BLE001 - re-raised as ProviderUnavailable
            last_error = exc

    raise ProviderUnavailable(
        f"LLM provider '{get_default_provider()}' failed after {attempts} attempts"
    ) from last_error

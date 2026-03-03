from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_models import ChatZhipuAI
import os
from functools import lru_cache
from dotenv import load_dotenv,  find_dotenv
from pydantic import SecretStr
import warnings



warnings.filterwarnings("ignore")   

load_dotenv(dotenv_path=r"F:\Files\Portfolio\Knowledge-Dungeon\.env", override=True)

def _require_env(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value:
        raise RuntimeError(f"{var_name} not found")
    return value


def get_default_provider() -> str:
    """Return default LLM provider name.

    Centralizes provider selection so all agents/API/CLI use the same model.
    """
    return os.getenv("LLM_PROVIDER", "groq")


@lru_cache(maxsize=8)
def _get_llm_cached(provider: str):
    """Create and cache an LLM client for a given provider."""
    if provider == "groq":
        groq_api_key = _require_env("GROQ_API_KEY")
        return ChatGroq(
            model="openai/gpt-oss-120b",
            api_key=SecretStr(groq_api_key),
        )
    if provider == "glm":
        glm_api_key = _require_env("GLM_API_KEY")
        return ChatZhipuAI(
            model="glm-4.7-flash",
            api_key=glm_api_key,
        )
    if provider == "gemini":
        google_api_key = _require_env("GOOGLE_API_KEY")
        return ChatGoogleGenerativeAI(
            model="gemini-3.1-flash-preview",
            api_key=google_api_key,
            response_format="text",
        )

    raise ValueError(f"Unknown provider: {provider}")


def get_llm(provider=None):
    """Return a shared LLM client.

    If provider is omitted, uses the `LLM_PROVIDER` env var (default: "groq").
    Instances are cached so repeated calls reuse the same client.
    """
    provider = provider or get_default_provider()
    return _get_llm_cached(provider)

def get_glm_llm():
    return get_llm("glm")

def get_gemini_llm():
    return get_llm("gemini")

if __name__ == "__main__":
    llm = get_gemini_llm()
    response = llm.invoke("What is the capital of France? Reply as JSON: {\"capital\": \"...\"} only.")
    print(response)

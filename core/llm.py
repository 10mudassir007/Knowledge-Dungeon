from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_models import ChatZhipuAI
import os
from dotenv import load_dotenv
import warnings

warnings.filterwarnings("ignore")   

load_dotenv()

def _require_env(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value:
        raise RuntimeError(f"{var_name} not found")
    return value




def get_llm(provider="groq"):
    if provider == "groq":
        groq_api_key = _require_env("GROQ_API_KEY")
        return ChatGroq(
            model="openai/gpt-oss-120b",
            api_key=groq_api_key,
        )
    elif provider == "glm":
        glm_api_key = _require_env("GLM_API_KEY")
        return ChatZhipuAI(
            model="glm-4.7-flash",
            api_key=glm_api_key,
        )
    elif provider == "gemini":
        google_api_key = _require_env("GOOGLE_API_KEY")
        return ChatGoogleGenerativeAI(
            model="gemini-3-flash-preview",
            api_key=google_api_key,
            response_format="text",
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")

def get_glm_llm():
    glm_api_key = _require_env("GLM_API_KEY")
    return ChatZhipuAI(
        model="glm-4.7-flash",
        api_key=glm_api_key,
    )

def get_gemini_llm():
    google_api_key = _require_env("GOOGLE_API_KEY")
    return ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview",
        api_key=google_api_key,
        response_format="text",
    )

if __name__ == "__main__":
    llm = get_gemini_llm()
    response = llm.invoke("What is the capital of France? Reply as JSON: {\"capital\": \"...\"} only.")
    print(response)
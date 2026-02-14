from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not found")


def get_llm():
    return ChatGroq(
        model="openai/gpt-oss-120b",
        api_key=GROQ_API_KEY
    )
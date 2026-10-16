"""Question generation with structured JSON output, validated and retried."""

import json
import logging
from typing import Any

from langchain.agents import create_agent
from pydantic import BaseModel, Field

from core.llm import ProviderUnavailable, get_llm, invoke_agent
from core.tools import get_search_tool
from agents.prompts import QUESTION_AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MAX_VALIDATION_RETRIES = 2


class QuestionDraft(BaseModel):
    """The structured shape we require from the question agent."""

    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    accepted_alternatives: list[str] = Field(default_factory=list)


class QuestionGenerationError(RuntimeError):
    """The agent never produced a usable question. Maps to HTTP 502."""


def _extract_content(response: Any) -> str:
    content = response["messages"][-1].content
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content and isinstance(content[-1], dict):
        return str(content[-1].get("text", ""))
    return str(content)


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    return cleaned.strip()


def _coerce_draft(content: str) -> QuestionDraft:
    """Parse and validate the agent's reply. Raises ValueError on any problem."""
    return QuestionDraft.model_validate(json.loads(_strip_code_fence(content)))


def generate_question(user_interest, user_age, history=None) -> QuestionDraft:
    """Generate a question, returning a validated QuestionDraft.

    Retries up to MAX_VALIDATION_RETRIES times when the model does not return
    valid JSON, then raises QuestionGenerationError. Provider failures raise
    ProviderUnavailable.
    """
    if history is None:
        history = []

    search_tool = get_search_tool()
    llm = get_llm()
    question_agent = create_agent(
        model=llm,
        system_prompt=QUESTION_AGENT_SYSTEM_PROMPT,
        tools=[search_tool] if search_tool else [],
    )

    recent = list(history)[-50:]
    payload = {
        "messages": (
            f"Generate a general knowledge question about: {user_interest}\n"
            f"The user is: {user_age} years old\n"
            f"Previous questions (do not repeat): {recent}\n"
            f"Search available: {'yes' if search_tool else 'no'}"
        )
    }

    last_error: Exception | None = None
    for attempt in range(MAX_VALIDATION_RETRIES + 1):
        try:
            response = invoke_agent(question_agent, payload)
        except ProviderUnavailable:
            raise

        try:
            draft = _coerce_draft(_extract_content(response))
        except Exception as exc:  # noqa: BLE001 - malformed output is expected
            last_error = exc
            logger.warning(
                "Question agent returned unusable output (attempt %s/%s): %s",
                attempt + 1,
                MAX_VALIDATION_RETRIES + 1,
                exc,
            )
            continue

        draft.question = draft.question.strip()
        draft.answer = draft.answer.strip()
        draft.accepted_alternatives = [alt.strip() for alt in draft.accepted_alternatives if alt.strip()]
        return draft

    raise QuestionGenerationError(
        "The question model did not return a valid question after "
        f"{MAX_VALIDATION_RETRIES + 1} attempts. Last error: {last_error}"
    )

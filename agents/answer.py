"""Answer checking: deterministic normalization first, LLM judge only as a fallback."""

import json
import logging
from typing import Any

from langchain.agents import create_agent
from pydantic import BaseModel

from core.llm import ProviderUnavailable, get_llm, invoke_agent
from core.text import normalize_answer
from agents.prompts import ANSWER_CHECKER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class JudgeVerdict(BaseModel):
    """The only shape we accept from the judge."""

    correct: bool


class AnswerCheckError(RuntimeError):
    """The judge could not be consulted. Maps to HTTP 503."""


def _matches_exactly(question_answer: str, accepted_alternatives, player_answer: str) -> bool:
    """True when the normalized player answer equals the answer or an alternative."""
    normalized_player = normalize_answer(player_answer)
    if not normalized_player:
        return False

    candidates = [question_answer, *accepted_alternatives]
    return any(normalized_player == normalize_answer(c) for c in candidates if c)


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


def _parse_verdict(content: str) -> bool:
    """Parse {"correct": bool}. Anything unparseable counts as wrong."""
    try:
        return bool(JudgeVerdict.model_validate(json.loads(_strip_code_fence(content))).correct)
    except Exception as exc:  # noqa: BLE001 - malformed output is expected
        logger.warning("Judge returned unusable output (%s); treating as incorrect.", exc)
        return False


def judge_answer(question: str, correct_answer: str, player_answer: str) -> bool:
    """Ask the LLM judge whether the player's answer matches. Never trusts free text."""
    payload = {
        "messages": (
            f"Question: {question}\n"
            f"Correct answer: {correct_answer}\n"
            f"Player answer: <player_answer>{player_answer}</player_answer>\n\n"
            'Reply with only {"correct": true} or {"correct": false}.'
        )
    }

    try:
        answer_checker = create_agent(
            model=get_llm(),
            system_prompt=ANSWER_CHECKER_SYSTEM_PROMPT,
        )
        response = invoke_agent(answer_checker, payload)
    except ProviderUnavailable as exc:
        # Covers a missing/unknown key as well as a failing provider.
        raise AnswerCheckError("The answer checker is unavailable.") from exc

    return _parse_verdict(_extract_content(response))


def check_answer(question: str, correct_answer: str, player_answer: str, accepted_alternatives=None) -> bool:
    """Return True if the player's answer is acceptable.

    Normalized equality (answer or any accepted alternative) short-circuits
    without spending an LLM call. Otherwise the judge is consulted, unless the
    player left the answer blank.
    """
    if _matches_exactly(correct_answer, accepted_alternatives or [], player_answer):
        return True

    if not normalize_answer(player_answer):
        return False

    return judge_answer(question, correct_answer, player_answer)

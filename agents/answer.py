from langchain.agents import create_agent
from agents.prompts import ANSWER_CHECKER_SYSTEM_PROMPT
from core.tools import increase_points, decrease_lives
from core.llm import get_llm
from typing import Any, cast


def check_answer(question, correct_answer, user_answer):
    """Checks the user's answer against the correct one and updates points/lives accordingly."""
    llm = get_llm()

    answer_checker = create_agent(
        model=llm,
        tools=[increase_points, decrease_lives],
        system_prompt=ANSWER_CHECKER_SYSTEM_PROMPT,
    )

    # Token that uniquely identifies this question instance for scoring guards.
    score_token = f"q::{(question or '').strip()}"

    response = answer_checker.invoke(
        {
            "messages": (
                f"Question: {question}\n"
                f"Correct answer: {correct_answer}\n"
                f"User answer: {user_answer}\n\n"
                "When calling tools, ALWAYS pass the token exactly as shown:\n"
                f"token={score_token}\n\n"
                "Only output Correct or Incorrect."
            )
        }
    )["messages"][-1].content

    if type(response) == str:
        return response

    return response[-1]["text"]


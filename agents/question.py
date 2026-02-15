from agents.prompts import QUESTION_AGENT_SYSTEM_PROMPT
from langchain.agents import create_agent
from core.tools import get_search_tool
from core.llm import get_llm
from typing import Any, cast



def generate_question(user_interest, user_age, history=None):
    """Generates a question based on the user's interest, age, and history of previous questions."""

    if history is None:
        history = []

    llm = get_llm()

    question_agent = create_agent(
        model=llm,
        system_prompt=QUESTION_AGENT_SYSTEM_PROMPT,
        tools=[get_search_tool()],
    )
    response = question_agent.invoke(
        {
            "messages": f"Generate a general knowledge question about: {user_interest}\n"
            f"The user is: {user_age} years old\n"
            f"Previous questions: {history[-100:]}"
        }
    )["messages"][-1].content
    if type(response) == str:
        return response

    return response[-1]['text']
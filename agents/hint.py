"""In-character hints that never reveal the answer."""

from langchain.agents import create_agent

from core.llm import get_llm, invoke_agent
from agents.prompts import HINT_AGENT_SYSTEM_PROMPT


def _extract_content(response):
    content = response["messages"][-1].content
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content and isinstance(content[-1], dict):
        return str(content[-1].get("text", ""))
    return str(content)


def get_hint(question, answer, user_interest):
    """Provide a hint for the given question without revealing the answer."""
    llm = get_llm()

    hint_giver = create_agent(
        model=llm,
        system_prompt=HINT_AGENT_SYSTEM_PROMPT,
    )

    response = invoke_agent(
        hint_giver,
        {
            "messages": (
                f"Give a hint according to the question:{question}\n"
                f"Its correct answer is : {answer},\n"
                f"Use a character according to the user interest: {user_interest} to get the hint from "
                "and the tone should be according to that character, "
                "if a character does not match the user interest, then use Gandalf. "
                "Do not state the answer."
            )
        },
    )

    return _extract_content(response)

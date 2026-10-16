"""In-world narration for the current level."""

from langchain.agents import create_agent

from core.llm import get_llm, invoke_agent
from agents.prompts import ENV_AGENT_SYSTEM_PROMPT


def _extract_content(response):
    content = response["messages"][-1].content
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content and isinstance(content[-1], dict):
        return str(content[-1].get("text", ""))
    return str(content)


def generate_environment(user_interest, user_age, level):
    """Generate a dynamic environment narration for the quiz game."""
    llm = get_llm()

    environment_agent = create_agent(
        model=llm,
        system_prompt=ENV_AGENT_SYSTEM_PROMPT,
    )

    response = invoke_agent(
        environment_agent,
        {
            "messages": (
                "Create a 2-3 line in-world welcome message for a quiz dungeon. "
                "Narrate in the voice of a fictional evil character that fits the user's interest when possible. "
                "If none fits, use a generic dark narrator.\n"
                f"User interest: {user_interest}\n"
                f"User age: {user_age}\n"
                f"Current level: {level}"
            )
        },
    )

    return _extract_content(response)

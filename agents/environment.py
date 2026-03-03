from langchain.agents import create_agent
from agents.prompts import ENV_AGENT_SYSTEM_PROMPT
from core.llm import get_llm


def generate_environment(
    user_interest,
    user_age,
    level,
    *,
    last_verdict=None,
    points=None,
    previous_environment=None,
):
    """Generates a dynamic environment for the quiz game.

    Optional context from the previous round makes the narration reactive:
      - last_verdict: "Correct" / "Incorrect" / None (first round)
      - points: current score
      - previous_environment: the text generated last round
    """

    llm = get_llm()

    environment_agent = create_agent(
        model=llm,
        system_prompt=ENV_AGENT_SYSTEM_PROMPT,
    )

    # Build context block for the previous round
    prev_context = ""
    if last_verdict is not None:
        prev_context += f"Previous result: The player answered {last_verdict}.\n"
    if points is not None:
        prev_context += f"Player's current score: {points} points.\n"
    if previous_environment:
        prev_context += f"Your previous narration was: \"{previous_environment}\"\n"
    if prev_context:
        prev_context += "Continue the story from where you left off. React to how the player did.\n"

    response = environment_agent.invoke(
        {
            "messages": (
                "Create a 2-3 line in-world welcome message for a quiz dungeon. "
                "Narrate in the voice of a fictional evil character that fits the user's interest when possible. "
                "If none fits, use a generic dark narrator.\n"
                f"User interest: {user_interest}\n"
                f"User age: {user_age}\n"
                f"Current level: {level}\n"
                f"{prev_context}"
            )
        }
    )["messages"][-1].content
    if type(response) == str:
        return response

    return response[-1]['text']
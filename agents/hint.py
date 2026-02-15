from agents.prompts import HINT_AGENT_SYSTEM_PROMPT
from langchain.agents import create_agent
from core.llm import get_llm
from typing import Any, cast



def get_hint(question, answer, user_interest):
    """Provides a hint for the given question without revealing the answer."""

    llm = get_llm()
    
    hint_giver = create_agent(
        model=llm,
        system_prompt=HINT_AGENT_SYSTEM_PROMPT
    )

    response = hint_giver.invoke(
        {
            "messages": f"Give a hint according to the question:{question}\nIts correct answer is : {answer},\nUse a character according to the user interest: {user_interest} to get the hint from and the tone should be according to that character, if a character does not match the user interest, then use Gandalf"
        }
    )["messages"][-1].content

    if type(response) == str:
        return response

    return response[-1]['text']


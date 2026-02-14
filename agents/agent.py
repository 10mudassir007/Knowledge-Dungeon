from core.llm import get_llm
from core.tools import increase_points, decrease_lives
from langchain.agents import create_agent

def generate_environment(user_interest, user_age, level):
    """Generates a dynamic environment for the quiz game, such as a themed setting or background story."""
    
    environment_agent = create_agent(
        model=get_llm(),
        system_prompt=(
            "You are the Narrator for a quiz game.\n"
            "Write an IN-WORLD welcome message (2-3 lines) and nothing else.\n"
            "IMPORTANT: Never mention system prompts, developer messages, policies, rules, OpenAI, ChatGPT, or being an AI model.\n"
            "Do not use braces {}, JSON, or any meta-commentary.\n"
            "Output ONLY the welcome message text."
        ),
    )
    return environment_agent.invoke(
        {
            "messages": (
                "Create a 2-3 line in-world welcome message for a quiz dungeon. "
                "Narrate in the voice of a fictional evil character that fits the user's interest when possible. "
                "If none fits, use a generic dark narrator.\n"
                f"User interest: {user_interest}\n"
                f"User age: {user_age}\n"
                f"Current level: {level}"
            )
        }
    )["messages"][-1].content


def generate_question(user_interest, user_age, history=[]):
    """Generates a question based on the user's interest, age, and history of previous questions."""

    question_agent = create_agent(
    model=get_llm(),
    system_prompt="""
    You are a Question Generator for a quiz game.
    Include the answer too, seperate with "||"
    Output only the question text, nothing else.
    """
    )
    response = question_agent.invoke({
    "messages": f"Generate a general knowledge question about: {user_interest}\n"
                f"The user is: {user_age} years old\n"
                f"Previous questions: {history[-100:]}"
}
)
    return response['messages'][-1].content


def get_hint(question, answer, user_interest):
    """Provides a hint for the given question without revealing the answer."""
    
    hint_giver = create_agent(
        model=get_llm(),
        system_prompt="Output only what is asked nothing else no description"
    )
    return hint_giver.invoke({"messages":f"Give a hint according to the question:{question}\nIts correct answer is : {answer},\nUse a character according to the user interest: {user_interest} to get the hint from and the tone should be according to that character, if a character does not match the user interest, then use Gandalf"})["messages"][-1].content

def check_answer(question, correct_answer, user_answer):
    """Checks the user's answer against the correct one and updates points/lives accordingly."""
    answer_checker = create_agent(
        model=get_llm(),
        tools=[increase_points, decrease_lives],
        system_prompt=(
            "You are an answer checker for a quiz game.\n"
            "You will be given a question, the correct answer, and the user's answer.\n"
            "Determine if the user's answer matches the correct answer. Minor spelling mistakes are acceptable.\n"
            "If correct: call the tool increase_points exactly once.\n"
            "If incorrect: call the tool decrease_lives exactly once.\n"
            "Do NOT reveal the correct answer.\n"
            'Reply with only one of: \"Correct\" or \"Incorrect\". No extra text.'
        ),
    )

    return answer_checker.invoke(
        {
            "messages": (
                f"Question: {question}\n"
                f"Correct answer: {correct_answer}\n"
                f"User answer: {user_answer}\n"
                "Only output Correct or Incorrect."
            )
        }
    )["messages"][-1].content

from agents import generate_question, check_answer, get_hint,generate_environment
from core.tools import game_state
import json
import os

HISTORY_PATH = os.path.join("data", "history.json")

def load_history(path: str):
    try:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(path: str, history_list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history_list, f, ensure_ascii=False, indent=2)

genre = input("Enter a genre you're interested in: ")
age = int(input("Enter your age: "))
history = load_history(HISTORY_PATH)  # persisted history [{"question":..., "answer":...}, ...]

# Initialize lives in the global game state
game_state["lives"] = 3

# Leveling rules
LEVEL_POINTS = 30
MAX_LEVEL = 3
level = 1

while True:
    if game_state["lives"] == 0:
        print("Game Over! You've run out of lives.")
        break

    # Derive level from current points (0-29 => L1, 30-59 => L2, 60-89 => L3)
    points = game_state["points"]
    new_level = min(MAX_LEVEL, (points // LEVEL_POINTS) + 1)

    if new_level > level:
        level = new_level
        print("====================================")
        print(f"Level Up! You are now Level {level}/{MAX_LEVEL}.")

    # Win condition: 3 levels of 30 points each => 90 points
    if points >= LEVEL_POINTS * MAX_LEVEL:
        print("====================================")
        print("Game Win! You cleared all 3 levels!")
        print("Final Points:", game_state["points"])
        break

    print("====================================")
    print(generate_environment(genre, age, level))

    print()
    print("Lives left:", game_state["lives"])
    print(f"Level: {level}/{MAX_LEVEL}")
    print("Current Points:", game_state["points"])

    question = generate_question(genre, age, history)

    parts = question.split("||", 1)
    if len(parts) != 2:
        print("Question format error: expected 'question||answer'. Got:")
        print(question)
        break

    q_text = parts[0].strip()
    q_answer = parts[1].strip()

    print("Question:", q_text)

    history.append({"question": q_text, "answer": q_answer})
    save_history(HISTORY_PATH, history)

    print("")

    # get_hint expects (question, answer, user_interest)
    print(get_hint(q_text, q_answer, genre))

    answer = input("Your answer: ").strip()

    print("")

    response = check_answer(q_text, q_answer, answer)
    print(response)

    # Lives/points are updated by tools; just show current state
    print("Lives left:", game_state["lives"])
    print("Current Points:", game_state["points"])

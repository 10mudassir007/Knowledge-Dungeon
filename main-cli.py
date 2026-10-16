"""Terminal version of Knowledge Dungeon.

Shares the game's rules with the API: both call core.rules.apply_answer, so
points and lives are decided in exactly one place. History lives in
data/history_cli.json so the CLI never writes the API's file.
"""

from agents import (
    AnswerCheckError,
    QuestionGenerationError,
    check_answer,
    generate_environment,
    generate_question,
    get_hint,
)
from core.history import HISTORY_LIMIT, HistoryStore
from core.llm import ProviderUnavailable
from core.rules import MAX_LEVEL, apply_answer, new_state

DATA_DIR = "data"
HISTORY_PATH = DATA_DIR + "/history_cli.json"


def _safe_call(label, func, *args):
    """Run an agent call, turning provider/validation failures into a message."""
    try:
        return func(*args)
    except (ProviderUnavailable, AnswerCheckError) as exc:
        print(f"[{label} unavailable] {exc}")
    except QuestionGenerationError as exc:
        print(f"[{label} failed] {exc}")
    return None


def play(history_store: HistoryStore) -> None:
    genre = input("Enter a genre you're interested in: ").strip()
    if not genre:
        print("A genre is required.")
        return

    try:
        age = int(input("Enter your age: ").strip())
    except ValueError:
        print("Age must be a number.")
        return

    state = new_state()
    session_history: list = []

    while True:
        if state.game_over:
            print("Game Over! You've run out of lives.")
            break

        print("====================================")

        environment = _safe_call("narrator", generate_environment, genre, age, state.level)
        if environment:
            print(environment)

        print()
        print("Lives left:", state.lives)
        print(f"Level: {state.level}/{MAX_LEVEL}")
        print("Current Points:", state.points)

        draft = _safe_call("question", generate_question, genre, age, session_history)
        if draft is None:
            print("Cannot continue without a question.")
            break

        print("Question:", draft.question)
        print()

        hint = _safe_call("hint", get_hint, draft.question, draft.answer, genre)
        if hint:
            print(hint)
        print()

        entry = {"question": draft.question, "answer": draft.answer}
        session_history.append(entry)
        del session_history[:-HISTORY_LIMIT]
        history_store.append(entry)

        player_answer = input("Your answer: ").strip()

        correct = _safe_call("answer checker", check_answer, draft.question, draft.answer, player_answer, draft.accepted_alternatives)
        if correct is None:
            print("Could not check that answer - it does not count.")
            continue

        state = apply_answer(state, bool(correct))

        print()
        print("Correct!" if correct else "Incorrect.")
        print("Lives left:", state.lives)
        print("Current Points:", state.points)

        if state.won:
            print("====================================")
            print("Game Win! You cleared all 3 levels!")
            print("Final Points:", state.points)
            break


def main() -> None:
    play(HistoryStore(HISTORY_PATH, limit=HISTORY_LIMIT))


if __name__ == "__main__":
    main()

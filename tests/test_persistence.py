"""History persistence: capping, atomic writes, and de-duplication."""

import json
import os

from core.history import HistoryStore
from core.text import normalize_answer


def _entries(count, prefix="Q"):
    return [{"question": f"{prefix}{i}", "answer": "a"} for i in range(count)]


def test_load_missing_file_is_empty(tmp_path):
    assert HistoryStore(str(tmp_path / "nope.json")).load() == []


def test_load_corrupt_file_is_empty(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("[{broken", encoding="utf-8")
    assert HistoryStore(str(path)).load() == []


def test_load_non_list_json_is_empty(tmp_path):
    path = tmp_path / "history.json"
    path.write_text('{"not": "a list"}', encoding="utf-8")
    assert HistoryStore(str(path)).load() == []


def test_append_creates_parent_directories(tmp_path):
    store = HistoryStore(str(tmp_path / "deep" / "nested" / "history.json"))
    store.append({"question": "Q", "answer": "A"})
    assert json.loads((tmp_path / "deep" / "nested" / "history.json").read_text(encoding="utf-8")) == [
        {"question": "Q", "answer": "A"}
    ]


def test_append_preserves_unicode(tmp_path):
    store = HistoryStore(str(tmp_path / "history.json"))
    store.append({"question": "¿Quién descubrió América?", "answer": "Cristóbal Colón"})
    assert store.load()[0]["answer"] == "Cristóbal Colón"


def test_append_caps_at_fifty_entries(tmp_path):
    store = HistoryStore(str(tmp_path / "history.json"))
    for entry in _entries(60):
        store.append(entry)

    stored = store.load()
    assert len(stored) == 50
    assert stored[0]["question"] == "Q10"
    assert stored[-1]["question"] == "Q59"


def test_write_is_atomic_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "history.json"
    store = HistoryStore(str(path))
    store.append({"question": "Q", "answer": "A"})

    leftovers = [name for name in os.listdir(tmp_path) if name.endswith(".tmp")]
    assert leftovers == []


def test_known_question_keys_are_normalized(tmp_path):
    store = HistoryStore(str(tmp_path / "history.json"))
    store.append({"question": "The Eiffel Tower.", "answer": "Paris"})
    keys = store.known_question_keys()
    assert keys == {normalize_answer("The Eiffel Tower.")}
    assert normalize_answer("the eiffel tower") in keys


def test_saving_empty_list_writes_empty_array(tmp_path):
    path = tmp_path / "history.json"
    HistoryStore(str(path)).save([])
    assert path.read_text(encoding="utf-8").strip() == "[]"


def test_append_survives_a_read_only_filesystem(tmp_path, monkeypatch):
    """Serverless mounts are read-only; history must fall back to memory."""
    store = HistoryStore(str(tmp_path / "history.json"))

    def deny(*args, **kwargs):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr("builtins.open", deny)

    entries = store.append({"question": "Q", "answer": "A"})
    assert entries == [{"question": "Q", "answer": "A"}]
    assert store.load() == [{"question": "Q", "answer": "A"}]
    assert store.known_question_keys() == {normalize_answer("Q")}


def _load_cli():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("main_cli", Path(__file__).resolve().parents[1] / "main-cli.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli


def test_cli_and_api_use_different_files():
    import main

    cli = _load_cli()

    assert main.HISTORY_PATH.endswith("history.json")
    assert cli.HISTORY_PATH.endswith("history_cli.json")
    assert main.HISTORY_PATH != cli.HISTORY_PATH


def test_cli_plays_a_full_game_with_the_shared_rules(tmp_path, monkeypatch):
    """The CLI scores through core.rules.apply_answer, like the API does."""
    import main

    cli = _load_cli()
    from agents.question import QuestionDraft

    asked = {"n": 0}

    def next_question(interest, age, history=None):
        asked["n"] += 1
        return QuestionDraft(question=f"Question {asked['n']}?", answer="42")

    monkeypatch.setattr(cli, "generate_question", next_question)
    monkeypatch.setattr(cli, "generate_environment", lambda *a: "The dungeon stirs.")
    monkeypatch.setattr(cli, "get_hint", lambda *a: "Think.")
    monkeypatch.setattr(cli, "check_answer", lambda q, a, player, alts=None: player.strip() == a)

    # 9 correct answers (90 points, all three levels) then three wrong ones:
    # scoring past 90 does not finish a run, only the last life does.
    answers = iter(["space", "21"] + ["42"] * 9 + ["nope"] * 3)
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))

    cli.play(HistoryStore(str(tmp_path / "history_cli.json")))

    history = json.loads((tmp_path / "history_cli.json").read_text(encoding="utf-8"))
    assert len(history) == 12
    assert history[0] == {"question": "Question 1?", "answer": "42"}
    assert history[11] == {"question": "Question 12?", "answer": "42"}
    # Same file the API never touches.
    assert not (tmp_path / "history.json").exists()
    assert main.HISTORY_PATH != str(tmp_path / "history_cli.json")

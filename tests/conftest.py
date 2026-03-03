"""conftest – shared fixtures for the Knowledge Dungeon test suite."""

import pytest
import os
import json
import tempfile


# ── Temp history file ───────────────────────────────────────────────
@pytest.fixture
def tmp_history_file(tmp_path):
    """Return a path to a temporary history.json inside tmp_path."""
    return str(tmp_path / "history.json")


@pytest.fixture
def tmp_history_with_data(tmp_path):
    """Return a path to a temp history.json pre-filled with two entries."""
    path = tmp_path / "history.json"
    data = [
        {"question": "What is 2+2?", "answer": "4"},
        {"question": "Capital of France?", "answer": "Paris"},
    ]
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


# ── Fake LLM response helpers ──────────────────────────────────────
class FakeAIMessage:
    """Mimics a LangChain AIMessage with a .content attribute."""

    def __init__(self, content):
        self.content = content


class FakeAgent:
    """Mimics an agent returned by create_agent; returns a canned response."""

    def __init__(self, response_text):
        self._response_text = response_text

    def invoke(self, payload):
        return {"messages": [FakeAIMessage(self._response_text)]}


@pytest.fixture
def patch_create_agent(monkeypatch):
    """Return a helper that patches create_agent on every agent module."""

    def _patch(response_text):
        """
        Parameters
        ----------
        response_text : str
            The canned string the fake agent will return.
        """
        fake = FakeAgent(response_text)
        factory = lambda **kwargs: fake

        # Patch on every module that imports create_agent
        import agents.environment as _env
        import agents.question as _q
        import agents.answer as _a
        import agents.hint as _h

        for mod in (_env, _q, _a, _h):
            monkeypatch.setattr(mod, "create_agent", factory)

    return _patch

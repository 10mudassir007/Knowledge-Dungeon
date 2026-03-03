"""Tests for missing / invalid API key handling across LLM providers and tools."""

import os
import pytest
from unittest.mock import patch


# ═══════════════════════════════════════════════════════════════════════
# Helper: clear the LRU cache between tests so env changes take effect
# ═══════════════════════════════════════════════════════════════════════
@pytest.fixture(autouse=True)
def _clear_llm_cache():
    """Clear the _get_llm_cached LRU cache before and after every test."""
    from core.llm import _get_llm_cached
    _get_llm_cached.cache_clear()
    yield
    _get_llm_cached.cache_clear()


# ═══════════════════════════════════════════════════════════════════════
# _require_env
# ═══════════════════════════════════════════════════════════════════════
class TestRequireEnv:
    def test_raises_when_var_missing(self):
        from core.llm import _require_env
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="MISSING_VAR not found"):
                _require_env("MISSING_VAR")

    def test_raises_when_var_empty(self):
        from core.llm import _require_env
        with patch.dict(os.environ, {"EMPTY_VAR": ""}):
            with pytest.raises(RuntimeError, match="EMPTY_VAR not found"):
                _require_env("EMPTY_VAR")

    def test_returns_value_when_set(self):
        from core.llm import _require_env
        with patch.dict(os.environ, {"MY_KEY": "abc123"}):
            assert _require_env("MY_KEY") == "abc123"


# ═══════════════════════════════════════════════════════════════════════
# Groq API key
# ═══════════════════════════════════════════════════════════════════════
class TestGroqApiKey:
    def test_missing_groq_key_raises_runtime_error(self):
        with patch.dict(os.environ, {}, clear=True):
            from core.llm import get_llm
            with pytest.raises(RuntimeError, match="GROQ_API_KEY not found"):
                get_llm("groq")

    def test_empty_groq_key_raises_runtime_error(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}, clear=True):
            from core.llm import get_llm
            with pytest.raises(RuntimeError, match="GROQ_API_KEY not found"):
                get_llm("groq")


# ═══════════════════════════════════════════════════════════════════════
# GLM API key
# ═══════════════════════════════════════════════════════════════════════
class TestGlmApiKey:
    def test_missing_glm_key_raises_runtime_error(self):
        with patch.dict(os.environ, {}, clear=True):
            from core.llm import get_llm
            with pytest.raises(RuntimeError, match="GLM_API_KEY not found"):
                get_llm("glm")

    def test_empty_glm_key_raises_runtime_error(self):
        with patch.dict(os.environ, {"GLM_API_KEY": ""}, clear=True):
            from core.llm import get_llm
            with pytest.raises(RuntimeError, match="GLM_API_KEY not found"):
                get_llm("glm")


# ═══════════════════════════════════════════════════════════════════════
# Gemini API key
# ═══════════════════════════════════════════════════════════════════════
class TestGeminiApiKey:
    def test_missing_google_key_raises_runtime_error(self):
        with patch.dict(os.environ, {}, clear=True):
            from core.llm import get_llm
            with pytest.raises(RuntimeError, match="GOOGLE_API_KEY not found"):
                get_llm("gemini")

    def test_empty_google_key_raises_runtime_error(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": ""}, clear=True):
            from core.llm import get_llm
            with pytest.raises(RuntimeError, match="GOOGLE_API_KEY not found"):
                get_llm("gemini")


# ═══════════════════════════════════════════════════════════════════════
# Unknown provider
# ═══════════════════════════════════════════════════════════════════════
class TestUnknownProvider:
    def test_unknown_provider_raises_value_error(self):
        from core.llm import get_llm
        with pytest.raises(ValueError, match="Unknown provider"):
            get_llm("nonexistent_provider")


# ═══════════════════════════════════════════════════════════════════════
# Default provider fallback
# ═══════════════════════════════════════════════════════════════════════
class TestDefaultProvider:
    def test_defaults_to_groq(self):
        from core.llm import get_default_provider
        with patch.dict(os.environ, {}, clear=True):
            assert get_default_provider() == "groq"

    def test_respects_env_override(self):
        from core.llm import get_default_provider
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini"}):
            assert get_default_provider() == "gemini"


# ═══════════════════════════════════════════════════════════════════════
# Tavily (search tool) API key
# ═══════════════════════════════════════════════════════════════════════
class TestTavilyApiKey:
    def test_missing_tavily_key_raises_runtime_error(self):
        with patch.dict(os.environ, {}, clear=True):
            from core.tools import get_search_tool
            with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
                get_search_tool()

    def test_empty_tavily_key_raises_runtime_error(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}, clear=True):
            from core.tools import get_search_tool
            with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
                get_search_tool()

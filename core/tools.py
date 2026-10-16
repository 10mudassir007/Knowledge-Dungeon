"""Optional web-search tool for the question agent.

Search is a nice-to-have: if no key is configured (or Tavily is unreachable)
`get_search_tool` returns None and the question agent falls back to the model's
own knowledge. Scoring tools used to live here and mutated a module-level
`game_state`; scoring is now pure and lives in `core/rules.py`.
"""

import logging
import os

from langchain_tavily import TavilySearch

logger = logging.getLogger(__name__)


def is_search_configured() -> bool:
    """True when a Tavily key is present. Never exposes the key itself."""
    return bool(os.getenv("TAVILY_API_KEY"))


def warn_if_search_unconfigured() -> None:
    """Log a single startup warning when search is unavailable."""
    if not is_search_configured():
        logger.warning(
            "TAVILY_API_KEY is not set - question generation will use the model's own knowledge."
        )


def get_search_tool():
    """Return a Tavily tool, or None when search is unavailable.

    Returning None (instead of raising) lets the question agent run in a
    degraded-but-working mode.
    """
    if not is_search_configured():
        return None

    try:
        return TavilySearch(
            max_results=5,
            topic="general",
            include_images=False,
        )
    except Exception as exc:  # noqa: BLE001 - search must never break the game
        logger.warning("Search tool unavailable (%s); continuing without search.", exc)
        return None

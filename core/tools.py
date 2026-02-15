from langchain.tools import tool
from langchain_tavily import TavilySearch
import os

# Track state and tool-call guards to prevent double-scoring.
game_state = {"points": 0, "lives": 3}
_last_score_token = None
_last_life_token = None


def _make_token(*parts) -> str:
  return "|".join(str(p) for p in parts if p is not None)


@tool
def increase_points(token: str = ""):
  """Increase points by 10.

  Pass a unique `token` per question (e.g., question text or session_id+question).
  If the tool is called multiple times with the same token, points are only
  increased once.
  """
  global _last_score_token
  if token and token == _last_score_token:
    return game_state["points"]

  game_state["points"] += 10
  _last_score_token = token or _last_score_token
  return game_state["points"]


@tool
def decrease_lives(token: str = ""):
  """Decrease lives by 1.

  Pass a unique `token` per question.
  If called multiple times with the same token, lives are only decreased once.
  """
  global _last_life_token
  if token and token == _last_life_token:
    return game_state["lives"]

  if game_state["lives"] > 0:
    game_state["lives"] -= 1
  _last_life_token = token or _last_life_token
  return game_state["lives"]


def get_search_tool():
  """
  Lazily create Tavily search tool only when needed.
  Prevents env/key errors when running agents that don't use search.
  """
  if not os.getenv("TAVILY_API_KEY"):
    raise RuntimeError("TAVILY_API_KEY not set, but search tool was requested.")
  return TavilySearch(
      max_results=5,
      topic="general",
      include_images=False,
  )
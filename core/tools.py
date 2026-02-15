from langchain.tools import tool
from langchain_tavily import TavilySearch

game_state = {"points": 0, "lives": 3} 

@tool
def increase_points():
  """Tool to increase points when the user's answer is correct."""
  game_state["points"] += 10
  return game_state["points"]


@tool
def decrease_lives():
  """Tool to decrease lives (health) when the user's answer is incorrect. Points are not changed."""
  if game_state["lives"] > 0:
    game_state["lives"] -= 1
  return game_state["lives"]


search_tool = TavilySearch(
    max_results=5,
    topic="general",
    include_images=False,
)
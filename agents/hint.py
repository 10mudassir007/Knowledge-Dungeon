"""In-character hints that never reveal the answer."""

import re

from langchain.agents import create_agent

from core.llm import get_llm, invoke_agent
from agents.prompts import HINT_AGENT_SYSTEM_PROMPT

# Models keep prefixing the hint with their own speaker label
# ("*Data (Starfleet's android)*: Think..." or "**Gandalf**: ..."). The client
# already renders its own glyph before the hint, so the label is noise. Only
# forms that are clearly labels qualify: emphasis-wrapped text, "Name (aside)",
# or the literal words Hint/Answer - each followed by a colon or dash.
_SPEAKER_LABEL = re.compile(
    r"^\s*(?:"
    r"\*{1,2}[^*\n]{1,120}\*{1,2}"
    r"|[A-Z][\w'’.-]{0,24}(?:\s+[A-Z][\w'’.-]{0,24}){0,2}\s*\([^)\n]{0,120}\)"
    r"|(?i:Hint|Answer)"
    r")\s*[:\-—–]\s*"
)

_LEADING_GLYPH = re.compile(r"^[✦✨🔮]\s*")

_QUOTE_PAIRS = {'"': '"', "'": "'", "“": "”", "‘": "’"}


def clean_hint(text):
    """Drop a speaker label or wrapper the model prefixed onto the hint."""
    text = _LEADING_GLYPH.sub("", text.strip())
    # Up to two labels: some models write "**Data (…)**:" - one nesting deep.
    for _ in range(2):
        text, count = _SPEAKER_LABEL.subn("", text, count=1)
        if not count:
            break
        text = text.strip()
    if len(text) >= 2 and _QUOTE_PAIRS.get(text[0]) == text[-1]:
        text = text[1:-1].strip()
    # A hint the model wrapped entirely in emphasis is not meant to show them.
    for marks in ("**", "*"):
        if text.startswith(marks) and text.endswith(marks) and len(text) > 2 * len(marks):
            inner = text[len(marks):-len(marks)]
            if "*" not in inner:
                text = inner.strip()
                break
    return text


def _extract_content(response):
    content = response["messages"][-1].content
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content and isinstance(content[-1], dict):
        return str(content[-1].get("text", ""))
    return str(content)


def get_hint(question, answer, user_interest):
    """Provide a hint for the given question without revealing the answer."""
    llm = get_llm()

    hint_giver = create_agent(
        model=llm,
        system_prompt=HINT_AGENT_SYSTEM_PROMPT,
    )

    response = invoke_agent(
        hint_giver,
        {
            "messages": (
                f"Give a hint according to the question:{question}\n"
                f"Its correct answer is : {answer},\n"
                f"Use a character according to the user interest: {user_interest} to get the hint from "
                "and the tone should be according to that character, "
                "if a character does not match the user interest, then use Gandalf. "
                "Do not state the answer."
            )
        },
    )

    return clean_hint(_extract_content(response))

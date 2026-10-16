"""Text normalization shared by answer checking and history de-duplication."""

import re
import unicodedata

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)
_LEADING_ARTICLES = ("the ", "an ", "a ")


def normalize_text(value: str) -> str:
    """Lowercase, NFKD-fold accents, drop punctuation, collapse whitespace.

    Used for history de-duplication, where the answer wording is irrelevant.
    """
    if not value:
        return ""
    folded = unicodedata.normalize("NFKD", value)
    # Strip combining marks left behind by NFKD ("e" + acute -> "e").
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.casefold()
    folded = _PUNCT_RE.sub(" ", folded)
    return _WS_RE.sub(" ", folded).strip()


def normalize_answer(value: str) -> str:
    """normalize_text plus removal of a single leading article.

    "The Eiffel Tower." and "eiffel tower" both normalize to "eiffel tower".
    """
    normalized = normalize_text(value)
    for article in _LEADING_ARTICLES:
        if normalized.startswith(article):
            return normalized[len(article):]
    return normalized

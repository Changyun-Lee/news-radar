from __future__ import annotations

import re
from typing import Final


SPACE_HYPHEN_RE: Final = re.compile(r"[\s\-‐‑‒–—―]+")


def normalize_keyword_value(value: str) -> str:
    return SPACE_HYPHEN_RE.sub("", value.casefold())


def keyword_gate_allows(text: str, keywords: tuple[str, ...]) -> bool:
    folded_text = text.casefold()
    normalized_text = normalize_keyword_value(text)
    for keyword in keywords:
        folded_keyword = keyword.casefold()
        if folded_keyword and folded_keyword in folded_text:
            return True
        normalized_keyword = normalize_keyword_value(keyword)
        if normalized_keyword and normalized_keyword in normalized_text:
            return True
    return False

from __future__ import annotations

from typing import Final

from .models import CollectionResult
from .store import SeenStore


HIGH_WATER_PREFIX: Final = "tg_high_water:"


def state_key(handle: str) -> str:
    return f"{HIGH_WATER_PREFIX}{handle}"


def read_high_water(store: SeenStore, handle: str) -> int | None:
    raw_value = store.get_state(state_key(handle))
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except ValueError:
        return None


def finalize_tgchannel(store: SeenStore, result: CollectionResult, unconsumed_urls: tuple[str, ...]) -> None:
    unconsumed = set(unconsumed_urls)
    for candidate in result.candidate_marks:
        blocked_values = tuple(
            mark.value for mark in result.item_marks if mark.scope == candidate.scope and mark.url in unconsumed
        )
        final_value = min(blocked_values) - 1 if blocked_values else candidate.value
        store.set_state(state_key(candidate.scope), str(final_value))

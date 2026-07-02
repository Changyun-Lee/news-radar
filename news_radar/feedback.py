from __future__ import annotations

from .config import Settings
from .http import post_json
from .json_helpers import list_or_empty, object_or_empty
from .models import JsonObject
from .store import SeenStore


def collect_feedback(settings: Settings, store: SeenStore) -> int:
    if not settings.telegram_bot_token:
        print("[feedback:skip] TELEGRAM_BOT_TOKEN missing", flush=True)
        return 0
    offset_raw = store.get_state("telegram_update_offset")
    offset = int(offset_raw) if offset_raw else 0
    payload: JsonObject = {"offset": offset, "timeout": 0, "allowed_updates": ["callback_query"]}
    data = post_json(f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates", payload)
    updates = list_or_empty(data.get("result"))
    saved = 0
    max_update_id = offset - 1
    for update_value in updates:
        update = object_or_empty(update_value)
        update_id_value = update.get("update_id")
        if isinstance(update_id_value, int):
            max_update_id = max(max_update_id, update_id_value)
        callback = object_or_empty(update.get("callback_query"))
        callback_id = callback.get("id")
        data_value = callback.get("data")
        if not isinstance(data_value, str) or not data_value.startswith("fb:"):
            continue
        parts = data_value.split(":")
        if len(parts) != 3:
            continue
        label = "good" if parts[1] == "g" else "bad"
        try:
            row_id = int(parts[2])
        except ValueError:
            continue
        store.add_feedback(row_id, label)
        saved += 1
        if isinstance(callback_id, str):
            post_json(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/answerCallbackQuery",
                {"callback_query_id": callback_id, "text": "기록했습니다."},
            )
    if max_update_id >= offset:
        store.set_state("telegram_update_offset", str(max_update_id + 1))
    print(f"[feedback] saved={saved}", flush=True)
    return saved

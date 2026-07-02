from __future__ import annotations

import json
from urllib import error

from .config import load_settings
from .console import configure_utf8_output
from .http import post_json
from .judge import OPENROUTER_URL
from .models import JsonObject
from .store import SeenStore


def _message_content(response: JsonObject) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("OpenRouter response did not include choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError("OpenRouter choice was not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("OpenRouter message was not an object")
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    raise RuntimeError("OpenRouter response content was not text")


def cap_lines(text: str, limit: int = 40) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    return "\n".join(lines[:limit]).strip() + "\n"


def main() -> None:
    configure_utf8_output()
    settings = load_settings()
    if not settings.openrouter_api_key:
        print("[distill:skip] OPENROUTER_API_KEY missing", flush=True)
        return
    store = SeenStore(settings.data_dir / "monitor.sqlite3")
    try:
        rows = store.get_distill_rows(7)
    finally:
        store.close()
    current = settings.criteria_file.read_text(encoding="utf-8")
    payload: JsonObject = {
        "model": settings.stage2_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Rewrite Korean alert criteria for a recall-first food, beverage, cosmetics news radar. "
                    "Keep it practical, under 40 lines, with separate overseas and domestic sections."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"현재 기준:\n{current}\n\n"
                    f"최근 7일 판정/피드백:\n{json.dumps(rows, ensure_ascii=False)}\n\n"
                    "기준 문서만 한국어로 출력하라."
                ),
            },
        ],
        "temperature": 0.2,
    }
    try:
        response = post_json(
            OPENROUTER_URL,
            payload,
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            timeout=60,
        )
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter API error {exc.code}: {detail}") from exc
    settings.criteria_file.write_text(cap_lines(_message_content(response)), encoding="utf-8")
    print(f"[distill:done] rows={len(rows)} file={settings.criteria_file}", flush=True)


if __name__ == "__main__":
    main()

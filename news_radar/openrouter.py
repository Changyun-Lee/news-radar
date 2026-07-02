from __future__ import annotations

from typing import Final
from urllib import error

from .http import post_json
from .json_helpers import list_or_empty, require_object
from .models import JsonObject


OPENROUTER_URL: Final = "https://openrouter.ai/api/v1/chat/completions"


def post_openrouter(api_key: str, payload: JsonObject, timeout: int = 60) -> JsonObject:
    try:
        return post_json(
            OPENROUTER_URL,
            payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter API error {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenRouter network error: {exc.reason}") from exc
    except OSError as exc:
        raise RuntimeError(f"OpenRouter network error: {exc}") from exc


def message_content(response: JsonObject) -> str:
    choices = list_or_empty(response.get("choices"))
    if not choices:
        raise RuntimeError("OpenRouter response did not include choices")
    first = require_object(choices[0])
    message = require_object(first.get("message"))
    content = message.get("content")
    if isinstance(content, str):
        return content
    raise RuntimeError("OpenRouter response content was not text")

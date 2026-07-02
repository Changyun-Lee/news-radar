from __future__ import annotations

import json
from typing import Final
from urllib import parse, request

from .models import JsonObject, JsonValue


DEFAULT_HEADERS: Final = {"User-Agent": "news-radar/1.0"}


class JsonResponseError(RuntimeError):
    pass


def _json_object(value: JsonValue) -> JsonObject:
    if isinstance(value, dict):
        return value
    raise JsonResponseError("JSON response was not an object")


def get_text(url: str, params: dict[str, str | int] | None = None, headers: dict[str, str] | None = None) -> str:
    query = "" if params is None else f"?{parse.urlencode(params)}"
    req = request.Request(f"{url}{query}", headers={**DEFAULT_HEADERS, **(headers or {})})
    with request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def get_json(url: str, params: dict[str, str | int], headers: dict[str, str] | None = None) -> JsonObject:
    return _json_object(json.loads(get_text(url, params, headers)))


def post_json(url: str, payload: JsonObject, headers: dict[str, str] | None = None, timeout: int = 45) -> JsonObject:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={**DEFAULT_HEADERS, "Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        return _json_object(json.loads(response.read().decode("utf-8", errors="replace")))

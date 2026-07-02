from __future__ import annotations

import json
from json import JSONDecodeError

from .models import JsonObject, JsonValue


class JsonShapeError(RuntimeError):
    pass


def require_object(value: JsonValue) -> JsonObject:
    if isinstance(value, dict):
        return value
    raise JsonShapeError("Expected JSON object")


def object_or_empty(value: JsonValue) -> JsonObject:
    if isinstance(value, dict):
        return value
    return {}


def list_or_empty(value: JsonValue) -> list[JsonValue]:
    if isinstance(value, list):
        return value
    return []


def extract_fenced_text(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 3 or not lines[-1].strip().startswith("```"):
        return stripped
    return "\n".join(lines[1:-1]).strip()


def parse_json_object(text: str) -> JsonObject:
    try:
        value: JsonValue = json.loads(extract_fenced_text(text))
    except JSONDecodeError:
        raise
    return require_object(value)

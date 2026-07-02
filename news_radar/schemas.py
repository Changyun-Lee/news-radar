from __future__ import annotations

from typing import Final

from .models import JsonObject


JUDGMENT_SCHEMA: Final[JsonObject] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "keep",
        "importance_score",
        "novelty_score",
        "confidence_score",
        "issue_key",
        "duplicate_of_issue_key",
        "summary_ko",
        "implication_ko",
        "reason_ko",
        "telegram_title_ko",
        "risk_flags",
    ],
    "properties": {
        "keep": {"type": "boolean"},
        "importance_score": {"type": "integer"},
        "novelty_score": {"type": "integer"},
        "confidence_score": {"type": "integer"},
        "issue_key": {"type": "string"},
        "duplicate_of_issue_key": {"type": "string"},
        "summary_ko": {"type": "string"},
        "implication_ko": {"type": "string"},
        "reason_ko": {"type": "string"},
        "telegram_title_ko": {"type": "string"},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
    },
}

STAGE1_SCHEMA: Final[JsonObject] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["relevant", "reason"],
    "properties": {
        "relevant": {"type": "boolean"},
        "reason": {"type": "string"},
    },
}


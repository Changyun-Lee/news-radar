from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import html
import re
from typing import Final


TAG_RE: Final = re.compile(r"<[^>]+>")


def clean_text(value: str | None) -> str:
    return html.unescape(TAG_RE.sub("", value or "")).strip()


def parse_pub_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

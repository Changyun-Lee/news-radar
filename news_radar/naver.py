from __future__ import annotations

from datetime import timezone
from email.utils import parsedate_to_datetime
import html
import re
from typing import Final

from .config import Company, Settings
from .http import get_json
from .models import Item, JsonObject, JsonValue


TAG_RE: Final = re.compile(r"<[^>]+>")


def clean_text(value: str) -> str:
    return html.unescape(TAG_RE.sub("", value)).strip()


def parse_pub_date(value: str) -> str:
    if not value:
        return ""
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def text_field(raw: JsonObject, key: str) -> str:
    value = raw.get(key)
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


def object_items(value: JsonValue) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


class NaverNewsClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def enabled(self) -> bool:
        return bool(
            (self.settings.naver_client_id and self.settings.naver_client_secret)
            or self.settings.kskill_proxy_base_url
        )

    def search(self, query: str) -> list[JsonObject]:
        if self.settings.naver_client_id and self.settings.naver_client_secret:
            return self._search_direct(query)
        if self.settings.kskill_proxy_base_url:
            return self._search_proxy(query)
        raise RuntimeError("Naver is not configured")

    def _search_direct(self, query: str) -> list[JsonObject]:
        data = get_json(
            "https://openapi.naver.com/v1/search/news.json",
            {"query": query, "display": self.settings.news_display, "sort": "date"},
            headers={
                "X-Naver-Client-Id": self.settings.naver_client_id,
                "X-Naver-Client-Secret": self.settings.naver_client_secret,
            },
        )
        return object_items(data.get("items"))

    def _search_proxy(self, query: str) -> list[JsonObject]:
        data = get_json(
            f"{self.settings.kskill_proxy_base_url}/v1/naver-news/search",
            {"q": query, "display": self.settings.news_display, "sort": "date"},
        )
        return object_items(data.get("items"))


def collect_company_news(client: NaverNewsClient, company: Company) -> list[Item]:
    query = company.aliases[0]
    items: list[Item] = []
    for raw in client.search(query):
        title = clean_text(text_field(raw, "title"))
        description = clean_text(text_field(raw, "description"))
        link = text_field(raw, "link")
        original_link = text_field(raw, "originallink") or text_field(raw, "original_link")
        published_at = text_field(raw, "pub_date_iso") or parse_pub_date(
            text_field(raw, "pubDate") or text_field(raw, "pub_date")
        )
        url = original_link or link
        if not title or not url:
            continue
        items.append(
            Item(
                source="domestic",
                stream=company.name,
                title=title,
                description=description,
                url=url,
                published_at=published_at,
            )
        )
    return items


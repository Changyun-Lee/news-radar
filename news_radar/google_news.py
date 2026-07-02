from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import html
import re
from typing import Final
from urllib import parse, request
import xml.etree.ElementTree as ET

from .config import OverseasQuery, load_overseas_queries, load_settings
from .console import configure_utf8_output
from .models import Item


GOOGLE_NEWS_URL: Final = "https://news.google.com/rss/search"
USER_AGENT: Final = "news-radar/1.0 (+https://github.com/)"
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


def rss_url(query: str) -> str:
    params = {
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    }
    return f"{GOOGLE_NEWS_URL}?{parse.urlencode(params)}"


def fetch_rss(query: str) -> str:
    req = request.Request(rss_url(query), headers={"User-Agent": USER_AGENT})
    with request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_rss(stream: str, xml_text: str, now: datetime | None = None) -> list[Item]:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(hours=48)
    root = ET.fromstring(xml_text)
    items: list[Item] = []
    for node in root.findall("./channel/item"):
        published_dt = parse_pub_date(node.findtext("pubDate"))
        if published_dt is None or published_dt < cutoff:
            continue
        title = clean_text(node.findtext("title"))
        link = clean_text(node.findtext("link"))
        description = clean_text(node.findtext("description"))
        source = clean_text(node.findtext("source"))
        if source and source not in title:
            description = f"{source} | {description}" if description else source
        if not title or not link:
            continue
        items.append(
            Item(
                source="overseas",
                stream=stream,
                title=title,
                description=description,
                url=link,
                published_at=published_dt.isoformat(),
            )
        )
    return items


def collect_query(query: OverseasQuery) -> list[Item]:
    return parse_rss(query.stream, fetch_rss(query.query))


def main() -> None:
    configure_utf8_output()
    settings = load_settings()
    queries = load_overseas_queries(settings.overseas_queries_file)
    for query in queries:
        items = collect_query(query)
        print(f"[rss] stream={query.stream} count={len(items)}", flush=True)


if __name__ == "__main__":
    main()

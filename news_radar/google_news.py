from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final
from urllib import parse, request
import xml.etree.ElementTree as ET

from .config import OverseasQuery, Settings, load_overseas_queries, load_settings
from .console import configure_utf8_output
from .models import CollectionResult, Item
from .text import clean_text, parse_pub_date


GOOGLE_NEWS_URL: Final = "https://news.google.com/rss/search"
USER_AGENT: Final = "news-radar/1.0 (+https://github.com/)"
OVERSEAS_SOURCE_BLOCKLIST_FILE: Final = Path("config/overseas_source_blocklist.txt")


@dataclass(frozen=True, slots=True)
class OverseasQueryResult:
    items: list[Item]
    skipped_kr: int


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


def _domain_from_url(raw_url: str) -> str:
    value = clean_text(raw_url).lower().strip(".")
    if not value:
        return ""
    parsed = parse.urlparse(value)
    if not parsed.netloc:
        parsed = parse.urlparse(f"//{value}")
    return (parsed.hostname or "").strip(".")


def _domain_matches(hostname: str, blocked_domain: str) -> bool:
    return hostname == blocked_domain or hostname.endswith(f".{blocked_domain}")


def load_overseas_source_blocklist(path: Path = OVERSEAS_SOURCE_BLOCKLIST_FILE) -> tuple[str, ...]:
    domains: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", maxsplit=1)[0].strip()
        if not line:
            continue
        domain = _domain_from_url(line)
        if domain and not domain.endswith(".kr"):
            domains.append(domain)
    return tuple(dict.fromkeys(domains))


def is_blocked_overseas_source_domain(raw_domain_or_url: str, blocked_domains: tuple[str, ...]) -> bool:
    hostname = _domain_from_url(raw_domain_or_url)
    if not hostname:
        return False
    return hostname.endswith(".kr") or any(_domain_matches(hostname, domain) for domain in blocked_domains)


def _rss_source_domain(node: ET.Element, link: str) -> str:
    source_node = node.find("source")
    if source_node is not None:
        source_url = clean_text(source_node.get("url"))
        if source_url:
            return _domain_from_url(source_url)
    return _domain_from_url(link)


def parse_rss(
    stream: str,
    xml_text: str,
    blocked_domains: tuple[str, ...],
    now: datetime | None = None,
) -> OverseasQueryResult:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(hours=48)
    root = ET.fromstring(xml_text)
    items: list[Item] = []
    skipped_kr = 0
    for node in root.findall("./channel/item"):
        published_dt = parse_pub_date(node.findtext("pubDate"))
        if published_dt is None or published_dt < cutoff:
            continue
        title = clean_text(node.findtext("title"))
        link = clean_text(node.findtext("link"))
        if not title or not link:
            continue
        source_domain = _rss_source_domain(node, link)
        if is_blocked_overseas_source_domain(source_domain, blocked_domains):
            skipped_kr += 1
            continue
        description = clean_text(node.findtext("description"))
        source = clean_text(node.findtext("source"))
        if source and source not in title:
            description = f"{source} | {description}" if description else source
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
    return OverseasQueryResult(items, skipped_kr)


def collect_query(query: OverseasQuery, blocked_domains: tuple[str, ...]) -> OverseasQueryResult:
    return parse_rss(query.stream, fetch_rss(query.query), blocked_domains)


def collect_overseas(settings: Settings) -> CollectionResult:
    items: list[Item] = []
    blocked_domains = load_overseas_source_blocklist()
    for query in load_overseas_queries(settings.overseas_queries_file):
        try:
            query_result = collect_query(query, blocked_domains)
        except (ET.ParseError, OSError, TimeoutError) as exc:
            print(f"[overseas:error] stream={query.stream} {exc}", flush=True)
            continue
        print(
            f"[overseas] stream={query.stream} collected={len(query_result.items)} "
            f"skipped_kr={query_result.skipped_kr}",
            flush=True,
        )
        items.extend(query_result.items)
    return CollectionResult(items, attempted=True)


def main() -> None:
    configure_utf8_output()
    settings = load_settings()
    queries = load_overseas_queries(settings.overseas_queries_file)
    blocked_domains = load_overseas_source_blocklist()
    for query in queries:
        result = collect_query(query, blocked_domains)
        print(f"[rss] stream={query.stream} count={len(result.items)} skipped_kr={result.skipped_kr}", flush=True)


if __name__ == "__main__":
    main()

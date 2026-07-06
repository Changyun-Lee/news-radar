from __future__ import annotations

from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
import time
from typing import Final, Literal, assert_never
from urllib import parse

from .config import Settings, load_companies
from .http import get_text
from .models import CollectionMark, CollectionResult, Item, ItemMark, SuppressionRecord
from .store import MENTOR_SHARED_SOURCE, SeenStore
from .tgchannel_keywords import keyword_gate_allows
from .tgchannel_state import read_high_water


ChannelMode = Literal["llm", "keyword", "suppress"]

TELEGRAM_WEB_URL: Final = "https://t.me/s"
USER_AGENT: Final = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 news-radar/1.0"
MAX_PAGES_PER_CHANNEL: Final = 50
PAGE_DELAY_SECONDS: Final = 0.4
SPACE_RE: Final = re.compile(r"[ \t\r\f\v]+")
URL_RE: Final = re.compile(r"https?://\S+")
SUPPRESSION_DEDUPE_RE: Final = re.compile(r"[\s-]+")


class TelegramChannelConfigError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TelegramChannel:
    stream: str
    handle: str
    mode: ChannelMode


@dataclass(frozen=True, slots=True)
class TelegramMessage:
    message_id: int
    text: str
    published_at: str


@dataclass(frozen=True, slots=True)
class ChannelCollection:
    items: tuple[Item, ...]
    fetched: int
    gated_out: int
    suppress_records: int
    suppress_duplicates: int
    attempted: bool
    candidate_mark: CollectionMark | None
    item_marks: tuple[ItemMark, ...]


class TelegramPageParser(HTMLParser):
    def __init__(self, handle: str) -> None:
        super().__init__(convert_charrefs=True)
        self.handle = handle.casefold()
        self.messages: list[TelegramMessage] = []
        self._message_id: int | None = None
        self._message_div_depth = 0
        self._text_div_depth = 0
        self._published_at = ""
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "br":
            self._append_break()
            return
        if tag == "time" and self._message_id is not None:
            self._published_at = attrs_dict.get("datetime", self._published_at)
            return
        if tag != "div":
            return
        class_attr = attrs_dict.get("class", "")
        if self._message_id is None:
            self._start_message(attrs_dict.get("data-post", ""), class_attr)
            return
        self._message_div_depth += 1
        if self._text_div_depth > 0:
            self._text_div_depth += 1
        elif _has_class(class_attr, "tgme_widget_message_text"):
            self._text_div_depth = 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self._append_break()

    def handle_endtag(self, tag: str) -> None:
        if tag != "div" or self._message_id is None:
            return
        if self._text_div_depth > 0:
            self._text_div_depth -= 1
        self._message_div_depth -= 1
        if self._message_div_depth == 0:
            self._finish_message()

    def handle_data(self, data: str) -> None:
        if self._text_div_depth > 0:
            self._text_parts.append(data)

    def _append_break(self) -> None:
        if self._text_div_depth > 0:
            self._text_parts.append("\n")

    def _start_message(self, data_post: str, class_attr: str) -> None:
        if not data_post or not _has_class(class_attr, "tgme_widget_message"):
            return
        message_id = _message_id_from_post(data_post, self.handle)
        if message_id is None:
            return
        self._message_id = message_id
        self._message_div_depth = 1
        self._text_div_depth = 0
        self._published_at = ""
        self._text_parts = []

    def _finish_message(self) -> None:
        if self._message_id is not None:
            self.messages.append(
                TelegramMessage(
                    message_id=self._message_id,
                    text=_normalize_message_text("".join(self._text_parts)),
                    published_at=self._published_at.strip(),
                )
            )
        self._message_id = None
        self._message_div_depth = 0
        self._text_div_depth = 0
        self._published_at = ""
        self._text_parts = []


def _has_class(class_attr: str, name: str) -> bool:
    return name in class_attr.split()


def _message_id_from_post(data_post: str, handle: str) -> int | None:
    post_handle, separator, raw_message_id = data_post.rpartition("/")
    if separator != "/" or post_handle.casefold() != handle:
        return None
    try:
        return int(raw_message_id)
    except ValueError:
        return None


def _normalize_message_text(value: str) -> str:
    lines = [SPACE_RE.sub(" ", line).strip() for line in value.replace("\xa0", " ").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _strip_comment(raw_line: str) -> str:
    return raw_line.split("#", maxsplit=1)[0].strip()


def _parse_mode(raw_mode: str, path: Path, line_no: int) -> ChannelMode:
    mode = raw_mode.strip().lower()
    match mode:
        case "llm":
            return "llm"
        case "keyword":
            return "keyword"
        case "suppress":
            return "suppress"
        case _:
            raise TelegramChannelConfigError(f"Expected mode 'llm', 'keyword', or 'suppress' at {path}:{line_no}")


def load_telegram_channels(path: Path) -> tuple[TelegramChannel, ...]:
    channels: list[TelegramChannel] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = _strip_comment(raw_line)
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3 or not parts[0] or not parts[1] or not parts[2]:
            raise TelegramChannelConfigError(f"Expected 'stream | handle | mode' at {path}:{line_no}")
        channels.append(TelegramChannel(stream=parts[0], handle=parts[1], mode=_parse_mode(parts[2], path, line_no)))
    if not channels:
        raise TelegramChannelConfigError(f"No Telegram channels loaded from {path}")
    return tuple(channels)


def load_breaking_keywords(keyword_path: Path, companies_path: Path) -> tuple[str, ...]:
    keywords: list[str] = []
    for raw_line in keyword_path.read_text(encoding="utf-8").splitlines():
        line = _strip_comment(raw_line)
        if not line:
            continue
        keywords.extend(keyword.strip() for keyword in line.split(",") if keyword.strip())
    for company in load_companies(companies_path):
        keywords.append(company.name)
        keywords.extend(company.aliases)
    return tuple(dict.fromkeys(keywords))


def fetch_channel_page(handle: str, before: int | None = None) -> str:
    params = None if before is None else {"before": before}
    url = f"{TELEGRAM_WEB_URL}/{parse.quote(handle, safe='')}"
    return get_text(url, params=params, headers={"User-Agent": USER_AGENT})


def parse_channel_page(handle: str, html_text: str) -> list[TelegramMessage]:
    parser = TelegramPageParser(handle)
    parser.feed(html_text)
    parser.close()
    return parser.messages


def _fetch_pages(channel: TelegramChannel, high_water: int | None) -> tuple[list[TelegramMessage], int | None, bool, bool]:
    messages: list[TelegramMessage] = []
    highest_message_id: int | None = None
    attempted = False
    before: int | None = None
    page_count = 0
    while page_count < MAX_PAGES_PER_CHANNEL:
        try:
            page_messages = parse_channel_page(channel.handle, fetch_channel_page(channel.handle, before))
        except (OSError, TimeoutError) as exc:
            print(f"[tgchannel:error] stream={channel.stream} before={before or ''} {exc}", flush=True)
            return messages, highest_message_id, False, attempted
        attempted = True
        if not page_messages:
            return messages, highest_message_id, True, attempted
        page_ids = [message.message_id for message in page_messages]
        page_count += 1
        messages.extend(page_messages)
        page_high = max(page_ids)
        highest_message_id = page_high if highest_message_id is None else max(highest_message_id, page_high)
        if high_water is None or any(message_id <= high_water for message_id in page_ids):
            return messages, highest_message_id, True, attempted
        before = min(page_ids)
        if page_count < MAX_PAGES_PER_CHANNEL:
            time.sleep(PAGE_DELAY_SECONDS)
    return messages, highest_message_id, True, attempted


def _message_to_item(channel: TelegramChannel, message: TelegramMessage, seed: bool) -> Item | None:
    if not message.text or not message.published_at:
        return None
    first_line = message.text.splitlines()[0]
    return Item(
        source="tgchannel",
        stream=channel.stream,
        title=first_line[:120].rstrip(),
        description=message.text[:600].rstrip(),
        url=f"https://t.me/{channel.handle}/{message.message_id}",
        published_at=message.published_at,
        seed=seed,
    )


def _record_url(channel: TelegramChannel, message: TelegramMessage) -> str:
    return f"https://t.me/{channel.handle}/{message.message_id}"


def _cap_title(title: str) -> str:
    return SPACE_RE.sub(" ", title).strip()[:120].rstrip()


def split_suppression_titles(text: str) -> tuple[str, ...]:
    lines = [SPACE_RE.sub(" ", line).strip() for line in text.splitlines() if line.strip()]
    url_lines = [line for line in lines if URL_RE.search(line)]
    if len(url_lines) < 2:
        return () if not lines else (_cap_title(lines[0]),)
    titles: list[str] = []
    for line in url_lines:
        title = _cap_title(URL_RE.sub(" ", line))
        if title:
            titles.append(title)
    return tuple(titles)


def _suppression_dedupe_key(title: str) -> str:
    normalized = SUPPRESSION_DEDUPE_RE.sub("", title.casefold())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _record_suppressions(channel: TelegramChannel, store: SeenStore, messages: list[TelegramMessage]) -> tuple[int, int]:
    records = 0
    duplicates = 0
    for message in messages:
        for title in split_suppression_titles(message.text):
            record = SuppressionRecord(
                source=MENTOR_SHARED_SOURCE,
                dedupe_key=_suppression_dedupe_key(title),
                stream=channel.stream,
                title=title,
                url=_record_url(channel, message),
                published_at=message.published_at,
            )
            if store.record_suppression(record):
                records += 1
            else:
                duplicates += 1
    return records, duplicates


def _collect_channel(
    channel: TelegramChannel,
    store: SeenStore,
    keywords: tuple[str, ...],
) -> ChannelCollection:
    high_water = read_high_water(store, channel.handle)
    messages, highest_message_id, completed, attempted = _fetch_pages(channel, high_water)
    candidates = messages if high_water is None else [message for message in messages if message.message_id > high_water]
    candidate_mark = CollectionMark(channel.handle, highest_message_id) if completed and highest_message_id is not None else None
    match channel.mode:
        case "llm":
            fetched_pairs = [
                (message, item)
                for message in candidates
                if (item := _message_to_item(channel, message, high_water is None)) is not None
            ]
            passed_pairs = fetched_pairs
            return ChannelCollection(
                items=tuple(item for _, item in passed_pairs),
                fetched=len(fetched_pairs),
                gated_out=0,
                suppress_records=0,
                suppress_duplicates=0,
                attempted=attempted,
                candidate_mark=candidate_mark,
                item_marks=tuple(ItemMark(item.url, channel.handle, message.message_id) for message, item in passed_pairs),
            )
        case "keyword":
            fetched_pairs = [
                (message, item)
                for message in candidates
                if (item := _message_to_item(channel, message, high_water is None)) is not None
            ]
            passed_pairs = [(message, item) for message, item in fetched_pairs if keyword_gate_allows(message.text, keywords)]
            return ChannelCollection(
                items=tuple(item for _, item in passed_pairs),
                fetched=len(fetched_pairs),
                gated_out=len(fetched_pairs) - len(passed_pairs),
                suppress_records=0,
                suppress_duplicates=0,
                attempted=attempted,
                candidate_mark=candidate_mark,
                item_marks=tuple(ItemMark(item.url, channel.handle, message.message_id) for message, item in passed_pairs),
            )
        case "suppress":
            records, duplicates = _record_suppressions(channel, store, candidates)
            return ChannelCollection(
                items=(),
                fetched=len(candidates),
                gated_out=0,
                suppress_records=records,
                suppress_duplicates=duplicates,
                attempted=attempted,
                candidate_mark=candidate_mark,
                item_marks=(),
            )
        case unreachable:
            assert_never(unreachable)


def collect_tgchannel(settings: Settings, store: SeenStore) -> CollectionResult:
    channels = load_telegram_channels(settings.telegram_channels_file)
    keywords = load_breaking_keywords(settings.breaking_keywords_file, settings.companies_file)
    items: list[Item] = []
    attempted = False
    candidate_marks: list[CollectionMark] = []
    item_marks: list[ItemMark] = []
    for channel in channels:
        channel_result = _collect_channel(channel, store, keywords)
        attempted = attempted or channel_result.attempted
        if channel_result.candidate_mark is not None:
            candidate_marks.append(channel_result.candidate_mark)
        item_marks.extend(channel_result.item_marks)
        match channel.mode:
            case "llm" | "keyword":
                print(
                    f"[tgchannel] stream={channel.stream} "
                    f"fetched={channel_result.fetched} gated_out={channel_result.gated_out} "
                    f"passed={len(channel_result.items)}",
                    flush=True,
                )
            case "suppress":
                print(
                    f"[tgchannel] stream={channel.stream} mode=suppress records={channel_result.suppress_records} "
                    f"duplicates={channel_result.suppress_duplicates} fetched={channel_result.fetched}",
                    flush=True,
                )
            case unreachable:
                assert_never(unreachable)
        items.extend(channel_result.items)
    return CollectionResult(items, attempted=attempted, candidate_marks=tuple(candidate_marks), item_marks=tuple(item_marks))

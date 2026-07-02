from __future__ import annotations

import argparse
from dataclasses import dataclass
import time
from typing import assert_never
from urllib import error
import xml.etree.ElementTree as ET

from .config import Settings, load_companies, load_overseas_queries, load_settings
from .console import configure_utf8_output
from .feedback import collect_feedback
from .google_news import collect_query
from .judge import CallLimitReached, CallLimiter, OpenRouterJudge
from .models import ArticleJudgment, Item, Source, Stage2Failure
from .naver import NaverNewsClient, collect_company_news
from .records import skip_record, stage1_record, stage2_record
from .store import SeenStore
from .telegram import TelegramClient


@dataclass(slots=True)
class RunStats:
    collected: int = 0
    new: int = 0
    seeded: int = 0
    skipped: int = 0
    sent: int = 0
    budget_skipped: int = 0
    errors: int = 0


@dataclass(frozen=True, slots=True)
class Runtime:
    settings: Settings
    store: SeenStore
    telegram: TelegramClient
    judge: OpenRouterJudge
    limiter: CallLimiter
    criteria_text: str


def collect_domestic(settings: Settings) -> list[Item]:
    client = NaverNewsClient(settings)
    if not client.enabled():
        print("[domestic:skip] Naver credentials/proxy missing", flush=True)
        return []
    items: list[Item] = []
    for company in load_companies(settings.companies_file):
        try:
            company_items = collect_company_news(client, company)
        except (RuntimeError, OSError, error.URLError) as exc:
            print(f"[domestic:error] stream={company.name} {exc}", flush=True)
            continue
        print(f"[domestic] stream={company.name} collected={len(company_items)}", flush=True)
        items.extend(company_items)
    return items


def collect_overseas(settings: Settings) -> list[Item]:
    items: list[Item] = []
    for query in load_overseas_queries(settings.overseas_queries_file):
        try:
            query_items = collect_query(query)
        except (ET.ParseError, OSError, error.URLError) as exc:
            print(f"[overseas:error] stream={query.stream} {exc}", flush=True)
            continue
        print(f"[overseas] stream={query.stream} collected={len(query_items)}", flush=True)
        items.extend(query_items)
    return items


def process_item(runtime: Runtime, item: Item, seed_only: bool, stats: RunStats) -> None:
    if runtime.store.has_seen(item):
        return
    if seed_only:
        if runtime.store.add_seen(item):
            stats.new += 1
            stats.seeded += 1
        print(f"[seed] {item.source} | {item.stream} | {item.title}", flush=True)
        return
    if not runtime.judge.enabled():
        runtime.store.add_seen(item)
        runtime.store.record_judgment(skip_record(item, "openrouter_key_missing", "OPENROUTER_API_KEY missing"))
        stats.new += 1
        stats.skipped += 1
        print(f"[llm:skip] {item.source} | {item.stream} | OPENROUTER_API_KEY missing | {item.title}", flush=True)
        return
    try:
        stage1 = runtime.judge.judge_relevance(item, runtime.limiter)
    except CallLimitReached:
        stats.budget_skipped += 1
        print(f"[budget:skip] {item.source} | {item.stream} | {item.title}", flush=True)
        return
    except RuntimeError as exc:
        stats.errors += 1
        print(f"[llm:error] stage=1 source={item.source} stream={item.stream} {exc}", flush=True)
        return
    if not stage1.relevant:
        runtime.store.add_seen(item)
        runtime.store.record_judgment(stage1_record(runtime.settings, item, stage1, "stage1_irrelevant"))
        stats.new += 1
        stats.skipped += 1
        print(f"[stage1:skip] {item.source} | {item.stream} | {stage1.reason} | {item.title}", flush=True)
        return
    history = runtime.store.get_recent_history(item.source, item.stream, 14, 12)
    try:
        stage2 = runtime.judge.judge_article(item, stage1, history, runtime.criteria_text, runtime.limiter)
    except CallLimitReached:
        stats.budget_skipped += 1
        print(f"[budget:skip] {item.source} | {item.stream} | stage=2 | {item.title}", flush=True)
        return
    except RuntimeError as exc:
        stats.errors += 1
        print(f"[llm:error] stage=2 source={item.source} stream={item.stream} {exc}", flush=True)
        return
    runtime.store.add_seen(item)
    should_send, decision = runtime.judge.should_send(stage1, stage2)
    row_id = runtime.store.record_judgment(stage2_record(runtime.settings, item, stage1, stage2, decision))
    stats.new += 1
    if not should_send:
        stats.skipped += 1
        print(f"[stage2:skip] {item.source} | {item.stream} | {decision} | {item.title}", flush=True)
        return
    match stage2:
        case ArticleJudgment() as judgment:
            runtime.telegram.send_judgment(row_id, item, judgment)
            runtime.store.mark_notified(item)
            runtime.store.mark_judgment_sent(row_id, decision)
            stats.sent += 1
            print(f"[send] {item.source} | {item.stream} | row_id={row_id} | {item.title}", flush=True)
        case Stage2Failure():
            stats.skipped += 1
        case unreachable:
            assert_never(unreachable)


def selected_sources(raw_source: str) -> tuple[Source, ...]:
    if raw_source == "all":
        return ("domestic", "overseas")
    if raw_source == "domestic":
        return ("domestic",)
    return ("overseas",)


def collect_source(source: Source, settings: Settings) -> list[Item]:
    match source:
        case "domestic":
            return collect_domestic(settings)
        case "overseas":
            return collect_overseas(settings)
        case unreachable:
            assert_never(unreachable)


def run_once(raw_source: str) -> RunStats:
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    store = SeenStore(settings.data_dir / "monitor.sqlite3")
    stats = RunStats()
    try:
        store.prune()
        collect_feedback(settings, store)
        criteria_text = settings.criteria_file.read_text(encoding="utf-8")
        runtime = Runtime(
            settings=settings,
            store=store,
            telegram=TelegramClient(settings),
            judge=OpenRouterJudge(settings),
            limiter=CallLimiter(settings.max_llm_calls_per_run),
            criteria_text=criteria_text,
        )
        for source in selected_sources(raw_source):
            seed_only = store.is_first_run(source) and settings.first_run_mode == "seed"
            items = collect_source(source, settings)
            stats.collected += len(items)
            for item in items:
                process_item(runtime, item, seed_only, stats)
            store.mark_initialized(source)
    finally:
        store.close()
    print(
        "[done] "
        f"source={raw_source} collected={stats.collected} new={stats.new} seeded={stats.seeded} "
        f"sent={stats.sent} skipped={stats.skipped} budget_skipped={stats.budget_skipped} "
        f"llm_calls={runtime.limiter.used if 'runtime' in locals() else 0} errors={stats.errors}",
        flush=True,
    )
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=("domestic", "overseas", "all"), default="all")
    return parser.parse_args()


def main() -> None:
    configure_utf8_output()
    args = parse_args()
    while True:
        settings = load_settings()
        run_once(args.source)
        if settings.run_once:
            print("[exit] RUN_ONCE=1", flush=True)
            return
        time.sleep(settings.check_interval_seconds)


if __name__ == "__main__":
    main()

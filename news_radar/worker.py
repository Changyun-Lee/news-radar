from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
import time
from typing import Final, assert_never

from .config import Settings, load_settings
from .console import configure_utf8_output
from .feedback import collect_feedback
from .google_news import collect_overseas
from .judge import CallLimitReached, CallLimiter, OpenRouterJudge
from .models import ArticleJudgment, CollectionResult, Item, Source, Stage2Failure
from .naver import collect_domestic
from .records import skip_record, stage1_record, stage2_record
from .store import SeenStore
from .telegram import TelegramClient
from .telegram_channels import collect_tgchannel


Collector = Callable[[Settings, SeenStore], CollectionResult]
COLLECTORS: Final[dict[Source, Collector]] = {
    "domestic": collect_domestic,
    "overseas": collect_overseas,
    "tgchannel": collect_tgchannel,
}
ALL_SOURCES: Final = "all"


class UnknownSourceError(ValueError):
    pass


@dataclass(slots=True)  # noqa: MUTABLE_OK
class RunStats:
    collected: int = 0
    new: int = 0
    seeded: int = 0
    skipped: int = 0
    sent: int = 0
    budget_skipped: int = 0
    circuit_skipped: int = 0
    errors: int = 0
    consecutive_judge_errors: int = 0
    llm_circuit_open: bool = False


@dataclass(frozen=True, slots=True)
class Runtime:
    settings: Settings
    store: SeenStore
    telegram: TelegramClient
    judge: OpenRouterJudge
    limiter: CallLimiter
    criteria_text: str


def record_judge_error(stats: RunStats, item: Item, stage: int, exc: RuntimeError | OSError) -> None:
    stats.errors += 1
    stats.consecutive_judge_errors += 1
    print(f"[llm:error] stage={stage} source={item.source} stream={item.stream} {exc}", flush=True)
    if stats.consecutive_judge_errors >= 3:
        stats.llm_circuit_open = True
        print("[llm:circuit-open] consecutive judge errors reached 3", flush=True)


def record_judge_success(stats: RunStats) -> None:
    stats.consecutive_judge_errors = 0


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
    if stats.llm_circuit_open:
        stats.circuit_skipped += 1
        print(f"[llm:circuit-open] {item.source} | {item.stream} | {item.title}", flush=True)
        return
    try:
        stage1 = runtime.judge.judge_relevance(item, runtime.criteria_text, runtime.limiter)
    except CallLimitReached:
        stats.budget_skipped += 1
        print(f"[budget:skip] {item.source} | {item.stream} | {item.title}", flush=True)
        return
    except (RuntimeError, OSError) as exc:
        record_judge_error(stats, item, 1, exc)
        return
    record_judge_success(stats)
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
    except (RuntimeError, OSError) as exc:
        record_judge_error(stats, item, 2, exc)
        return
    record_judge_success(stats)
    should_send, decision = runtime.judge.should_send(stage1, stage2)
    if not should_send:
        runtime.store.add_seen(item)
        runtime.store.record_judgment(stage2_record(runtime.settings, item, stage1, stage2, decision))
        stats.new += 1
        stats.skipped += 1
        print(f"[stage2:skip] {item.source} | {item.stream} | {decision} | {item.title}", flush=True)
        return
    match stage2:
        case ArticleJudgment() as judgment:
            row_id = runtime.store.record_judgment(stage2_record(runtime.settings, item, stage1, stage2, decision))
            try:
                runtime.telegram.send_judgment(row_id, item, judgment)
            except (OSError, TimeoutError) as exc:
                runtime.store.delete_judgment(row_id)
                stats.errors += 1
                print(f"[telegram:error] source={item.source} stream={item.stream} row_id={row_id} {exc}", flush=True)
                return
            runtime.store.add_seen(item)
            runtime.store.mark_notified(item)
            runtime.store.mark_judgment_sent(row_id, decision)
            stats.new += 1
            stats.sent += 1
            print(f"[send] {item.source} | {item.stream} | row_id={row_id} | {item.title}", flush=True)
        case Stage2Failure():
            stats.skipped += 1
        case unreachable:
            assert_never(unreachable)


def selected_sources(raw_source: str) -> tuple[Source, ...]:
    if raw_source == ALL_SOURCES:
        return tuple(COLLECTORS)
    if raw_source in COLLECTORS:
        return (raw_source,)
    raise UnknownSourceError(f"Unknown source: {raw_source}")


def collect_source(source: Source, settings: Settings, store: SeenStore) -> CollectionResult:
    collector = COLLECTORS.get(source)
    if collector is None:
        raise UnknownSourceError(f"Unknown source: {source}")
    return collector(settings, store)


def run_once(raw_source: str) -> RunStats:
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    store = SeenStore(settings.data_dir / "monitor.sqlite3")
    stats = RunStats()
    limiter = CallLimiter(settings.max_llm_calls_per_run)
    try:
        store.prune()
        try:
            collect_feedback(settings, store)
        except (RuntimeError, OSError, TimeoutError, ValueError) as exc:
            stats.errors += 1
            print(f"[feedback:error] {exc}", flush=True)
        criteria_text = settings.criteria_file.read_text(encoding="utf-8")
        runtime = Runtime(
            settings=settings,
            store=store,
            telegram=TelegramClient(settings),
            judge=OpenRouterJudge(settings),
            limiter=limiter,
            criteria_text=criteria_text,
        )
        for source in selected_sources(raw_source):
            is_first_run = store.is_first_run(source)
            seed_only = is_first_run and settings.first_run_mode == "seed"
            result = collect_source(source, settings, store)
            stats.collected += len(result.items)
            for item in result.items:
                process_item(runtime, item, seed_only, stats)
            if is_first_run and result.attempted:
                store.mark_initialized(source)
    finally:
        store.close()
    print(
        "[done] "
        f"source={raw_source} collected={stats.collected} new={stats.new} seeded={stats.seeded} "
        f"sent={stats.sent} skipped={stats.skipped} budget_skipped={stats.budget_skipped} "
        f"circuit_skipped={stats.circuit_skipped} llm_calls={limiter.used} errors={stats.errors}",
        flush=True,
    )
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=(*COLLECTORS, ALL_SOURCES), default=ALL_SOURCES)
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

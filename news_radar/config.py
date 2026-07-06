from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


class SettingsConfigError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Company:
    name: str
    aliases: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True, slots=True)
class OverseasQuery:
    stream: str
    query: str


@dataclass(frozen=True, slots=True)
class Settings:
    naver_client_id: str
    naver_client_secret: str
    kskill_proxy_base_url: str
    telegram_bot_token: str
    telegram_chat_id: str
    openrouter_api_key: str
    dart_api_key: str
    dart_lookback_days: int
    stage1_model: str
    stage2_model: str
    distill_model: str
    max_llm_calls_per_run: int
    min_send_importance: int
    mentor_shared_hours: int
    mentor_shared_limit: int
    check_interval_seconds: int
    news_display: int
    send_telegram: bool
    run_once: bool
    first_run_mode: str
    data_dir: Path
    companies_file: Path
    overseas_queries_file: Path
    telegram_channels_file: Path
    breaking_keywords_file: Path
    criteria_file: Path


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def env_str(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip()


def load_settings() -> Settings:
    first_run_mode = os.getenv("FIRST_RUN_MODE", "seed").strip().lower()
    if first_run_mode not in {"seed", "notify"}:
        raise SettingsConfigError("FIRST_RUN_MODE must be 'seed' or 'notify'")
    return Settings(
        naver_client_id=env_str("NAVER_CLIENT_ID"),
        naver_client_secret=env_str("NAVER_CLIENT_SECRET"),
        kskill_proxy_base_url=env_str("KSKILL_PROXY_BASE_URL").rstrip("/"),
        telegram_bot_token=env_str("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=env_str("TELEGRAM_CHAT_ID"),
        openrouter_api_key=env_str("OPENROUTER_API_KEY"),
        dart_api_key=env_str("API_K_DART") or env_str("DART_API_KEY"),
        dart_lookback_days=env_int("DART_LOOKBACK_DAYS", 2),
        stage1_model=env_str("STAGE1_MODEL", "google/gemini-2.5-flash-lite"),
        stage2_model=env_str("STAGE2_MODEL", "google/gemini-2.5-flash"),
        distill_model=env_str("DISTILL_MODEL", "google/gemini-3.5-flash"),
        max_llm_calls_per_run=env_int("MAX_LLM_CALLS_PER_RUN", 40),
        min_send_importance=env_int("MIN_SEND_IMPORTANCE", 4),
        mentor_shared_hours=env_int("MENTOR_SHARED_HOURS", 48),
        mentor_shared_limit=env_int("MENTOR_SHARED_LIMIT", 30),
        check_interval_seconds=env_int("CHECK_INTERVAL_SECONDS", 600),
        news_display=env_int("NEWS_DISPLAY", 10),
        send_telegram=env_bool("SEND_TELEGRAM", False),
        run_once=env_bool("RUN_ONCE", False),
        first_run_mode=first_run_mode,
        data_dir=Path(os.getenv("DATA_DIR", "data")),
        companies_file=Path(os.getenv("COMPANIES_FILE", "config/companies.txt")),
        overseas_queries_file=Path(os.getenv("OVERSEAS_QUERIES_FILE", "config/overseas_queries.txt")),
        telegram_channels_file=Path(os.getenv("TELEGRAM_CHANNELS_FILE", "config/telegram_channels.txt")),
        breaking_keywords_file=Path(os.getenv("BREAKING_KEYWORDS_FILE", "config/breaking_keywords.txt")),
        criteria_file=Path(os.getenv("CRITERIA_FILE", "prompts/criteria_ko.md")),
    )


def load_companies(path: Path) -> list[Company]:
    companies: list[Company] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if not parts or not parts[0]:
            raise SettingsConfigError(f"Missing company name at {path}:{line_no}")
        aliases_raw = parts[1] if len(parts) > 1 and parts[1] else parts[0]
        aliases = tuple(dict.fromkeys(alias.strip() for alias in aliases_raw.split(",") if alias.strip()))
        note = parts[2] if len(parts) > 2 else ""
        companies.append(Company(name=parts[0], aliases=aliases or (parts[0],), note=note))
    if not companies:
        raise SettingsConfigError(f"No companies loaded from {path}")
    return companies


def load_overseas_queries(path: Path) -> list[OverseasQuery]:
    queries: list[OverseasQuery] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|", maxsplit=1)]
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise SettingsConfigError(f"Expected 'stream | query' at {path}:{line_no}")
        queries.append(OverseasQuery(stream=parts[0], query=parts[1]))
    if not queries:
        raise SettingsConfigError(f"No overseas queries loaded from {path}")
    return queries

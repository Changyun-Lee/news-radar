from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib import parse, request
import xml.etree.ElementTree as ET
import zipfile

from .config import Company, Settings, load_companies
from .http import get_json
from .models import CollectionResult, Item, JsonObject, JsonValue

if TYPE_CHECKING:
    from .store import SeenStore


DART_LIST_URL: Final = "https://opendart.fss.or.kr/api/list.json"
DART_CORP_CODE_URL: Final = "https://opendart.fss.or.kr/api/corpCode.xml"
DART_VIEWER_URL: Final = "https://dart.fss.or.kr/dsaf001/main.do"
DART_CACHE_NAME: Final = "dart_corp_codes.json"
EXCLUDED_REPORT_NAME: Final = "임원주요주주특정증권등소유상황보고서"
KST: Final = timezone(timedelta(hours=9))


class DartCollectionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CorpCodeEntry:
    corp_name: str
    corp_code: str


@dataclass(frozen=True, slots=True)
class DartCompanyResult:
    items: list[Item]
    excluded: int


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


def normalize_report_name(report_name: str) -> str:
    return "".join(char for char in report_name if not char.isspace() and char not in "ㆍ·.")


def is_excluded_report(report_name: str) -> bool:
    return EXCLUDED_REPORT_NAME in normalize_report_name(report_name)


class DartClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cache_path = settings.data_dir / DART_CACHE_NAME
        self._corp_code_cache: dict[str, str] | None = None

    def enabled(self) -> bool:
        return bool(self.settings.dart_api_key)

    def ensure_corp_code_cache(self, companies: tuple[Company, ...]) -> None:
        cache = self._load_cache()
        missing = tuple(company for company in companies if company.name not in cache)
        if missing:
            self._refresh_cache(cache, missing)

    def corp_code_for(self, company: Company) -> str | None:
        cache = self._load_cache()
        if company.name not in cache:
            cache = self._refresh_cache(cache, (company,))
        corp_code = cache.get(company.name, "")
        return corp_code or None

    def list_filings(self, company: Company, corp_code: str) -> list[JsonObject]:
        end = datetime.now(KST).date()
        begin = end - timedelta(days=self.settings.dart_lookback_days)
        try:
            data = get_json(
                DART_LIST_URL,
                {
                    "crtfc_key": self.settings.dart_api_key,
                    "corp_code": corp_code,
                    "bgn_de": begin.strftime("%Y%m%d"),
                    "end_de": end.strftime("%Y%m%d"),
                    "sort": "date",
                    "sort_mth": "desc",
                    "page_count": 30,
                },
            )
        except (OSError, TimeoutError, JSONDecodeError):
            raise DartCollectionError(f"DART list request failed for {company.name}") from None
        status = text_field(data, "status")
        if status == "013":
            return []
        if status != "000":
            message = text_field(data, "message")
            raise DartCollectionError(f"DART list failed for {company.name}: {status} {message}")
        return object_items(data.get("list"))

    def _load_cache(self) -> dict[str, str]:
        if self._corp_code_cache is not None:
            return self._corp_code_cache
        try:
            raw: JsonValue = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self._corp_code_cache = {}
            return self._corp_code_cache
        except (OSError, JSONDecodeError):
            print("[dart:cache] unreadable cache; refreshing", flush=True)
            self._corp_code_cache = {}
            return self._corp_code_cache
        if not isinstance(raw, dict):
            print("[dart:cache] invalid cache shape; refreshing", flush=True)
            self._corp_code_cache = {}
            return self._corp_code_cache
        self._corp_code_cache = {str(name): str(code) for name, code in raw.items()}
        return self._corp_code_cache

    def _refresh_cache(self, cache: dict[str, str], companies: tuple[Company, ...]) -> dict[str, str]:
        entries = self._download_corp_codes()
        by_name = {entry.corp_name: entry.corp_code for entry in entries}
        refreshed = dict(cache)
        for company in companies:
            refreshed[company.name] = resolve_corp_code(company, by_name) or ""
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(refreshed, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        self._corp_code_cache = refreshed
        return refreshed

    def _download_corp_codes(self) -> list[CorpCodeEntry]:
        url = f"{DART_CORP_CODE_URL}?{parse.urlencode({'crtfc_key': self.settings.dart_api_key})}"
        try:
            req = request.Request(url, headers={"User-Agent": "news-radar/1.0"})
            with request.urlopen(req, timeout=60) as response:
                payload = response.read()
            with zipfile.ZipFile(BytesIO(payload)) as zipped:
                xml_bytes = zipped.read("CORPCODE.xml")
            root = ET.fromstring(xml_bytes)
        except (OSError, TimeoutError, zipfile.BadZipFile, KeyError, ET.ParseError):
            raise DartCollectionError("DART corpCode cache refresh failed") from None
        entries: list[CorpCodeEntry] = []
        for node in root.findall("list"):
            corp_name = (node.findtext("corp_name") or "").strip()
            corp_code = (node.findtext("corp_code") or "").strip()
            if corp_name and corp_code:
                entries.append(CorpCodeEntry(corp_name=corp_name, corp_code=corp_code))
        return entries


def resolve_corp_code(company: Company, by_name: dict[str, str]) -> str | None:
    exact_names = (company.name, *company.aliases)
    for exact_name in exact_names:
        corp_code = by_name.get(exact_name)
        if corp_code:
            return corp_code
    return None


def collect_company_filings(client: DartClient, company: Company) -> DartCompanyResult:
    corp_code = client.corp_code_for(company)
    if corp_code is None:
        print(f"[dart:skip-nocode] stream={company.name}", flush=True)
        return DartCompanyResult([], 0)
    items: list[Item] = []
    excluded = 0
    for raw in client.list_filings(company, corp_code):
        report_name = text_field(raw, "report_nm")
        receipt_no = text_field(raw, "rcept_no")
        if not report_name or not receipt_no:
            continue
        if is_excluded_report(report_name):
            excluded += 1
            continue
        filer = text_field(raw, "flr_nm") or text_field(raw, "corp_name")
        description = f"{filer} | {report_name}" if filer else report_name
        items.append(
            Item(
                source="dart",
                stream=company.name,
                title=report_name,
                description=description,
                url=f"{DART_VIEWER_URL}?rcpNo={receipt_no}",
                published_at=text_field(raw, "rcept_dt"),
            )
        )
    return DartCompanyResult(items, excluded)


def collect_dart(settings: Settings, store: SeenStore | None = None) -> CollectionResult:
    client = DartClient(settings)
    if not client.enabled():
        print("[dart:skip] API_K_DART/DART_API_KEY missing", flush=True)
        return CollectionResult([], attempted=False)
    items: list[Item] = []
    excluded_total = 0
    companies = tuple(load_companies(settings.companies_file))
    try:
        client.ensure_corp_code_cache(companies)
    except DartCollectionError as exc:
        # 부트스트랩 실패는 시드를 소진하면 안 됨 — 다음 실행에서 재시도
        print(f"[dart:error] {exc}", flush=True)
        return CollectionResult([], attempted=False)
    for company in companies:
        try:
            result = collect_company_filings(client, company)
        except DartCollectionError as exc:
            print(f"[dart:error] stream={company.name} {exc}", flush=True)
            continue
        excluded_total += result.excluded
        print(
            f"[dart] stream={company.name} collected={len(result.items)} excluded={result.excluded}",
            flush=True,
        )
        items.extend(result.items)
    if excluded_total:
        print(f"[dart:excluded] count={excluded_total}", flush=True)
    return CollectionResult(items, attempted=True)

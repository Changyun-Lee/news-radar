from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


Source: TypeAlias = str
JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class Item:
    source: Source
    stream: str
    title: str
    description: str
    url: str
    published_at: str

    @property
    def dedupe_key(self) -> str:
        return self.url


@dataclass(frozen=True, slots=True)
class Stage1Result:
    relevant: bool
    reason: str
    risk_flags: tuple[str, ...]
    raw_response: str


@dataclass(frozen=True, slots=True)
class ArticleJudgment:
    keep: bool
    importance_score: int
    novelty_score: int
    confidence_score: int
    issue_key: str
    duplicate_of_issue_key: str
    summary_ko: str
    implication_ko: str
    reason_ko: str
    telegram_title_ko: str
    risk_flags: tuple[str, ...]
    raw_response: str


@dataclass(frozen=True, slots=True)
class Stage2Failure:
    reason: str
    raw_response: str
    risk_flags: tuple[str, ...]


Stage2Result: TypeAlias = ArticleJudgment | Stage2Failure


@dataclass(frozen=True, slots=True)
class JudgmentRecord:
    item: Item
    stage1_relevant: bool
    stage1_reason: str
    stage1_model: str
    stage2_model: str
    raw_response: str
    importance_score: int
    novelty_score: int
    confidence_score: int
    issue_key: str
    duplicate_of_issue_key: str
    summary_ko: str
    implication_ko: str
    reason_ko: str
    telegram_title_ko: str
    risk_flags: tuple[str, ...]
    decision: str


@dataclass(frozen=True, slots=True)
class CollectionResult:
    items: list[Item]
    attempted: bool


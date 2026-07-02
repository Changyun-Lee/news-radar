from __future__ import annotations

from dataclasses import dataclass
import json
from json import JSONDecodeError
from typing import Final, assert_never
from urllib import error

from .config import Settings
from .http import post_json
from .models import ArticleJudgment, Item, JsonObject, JsonValue, Stage1Result, Stage2Failure, Stage2Result
from .schemas import JUDGMENT_SCHEMA, STAGE1_SCHEMA


OPENROUTER_URL: Final = "https://openrouter.ai/api/v1/chat/completions"
PROMPT_VERSION: Final = "news-radar-v1"


class CallLimitReached(RuntimeError):
    pass


@dataclass(slots=True)
class CallLimiter:
    limit: int
    used: int = 0

    def claim(self) -> None:
        if self.used >= self.limit:
            raise CallLimitReached("MAX_LLM_CALLS_PER_RUN exhausted")
        self.used += 1


def _clamp_score(value: JsonValue) -> int:
    if isinstance(value, bool) or value is None:
        return 1
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(5, score))


def _as_object(value: JsonValue) -> JsonObject:
    if isinstance(value, dict):
        return value
    raise RuntimeError("Expected JSON object")


def _as_list(value: JsonValue) -> list[JsonValue]:
    if isinstance(value, list):
        return value
    return []


def _extract_json_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def _parse_json_object(text: str) -> JsonObject:
    return _as_object(json.loads(_extract_json_text(text)))


def _message_content(response: JsonObject) -> str:
    choices = _as_list(response.get("choices"))
    if not choices:
        raise RuntimeError("OpenRouter response did not include choices")
    first = _as_object(choices[0])
    message = _as_object(first.get("message"))
    content = message.get("content")
    if isinstance(content, str):
        return content
    raise RuntimeError("OpenRouter response content was not text")


def _flags(value: JsonValue) -> tuple[str, ...]:
    return tuple(str(flag) for flag in _as_list(value) if str(flag).strip())


def judgment_from_data(data: JsonObject, raw_response: str) -> ArticleJudgment:
    return ArticleJudgment(
        keep=bool(data.get("keep", False)),
        send=bool(data.get("send", False)),
        importance_score=_clamp_score(data.get("importance_score")),
        novelty_score=_clamp_score(data.get("novelty_score")),
        confidence_score=_clamp_score(data.get("confidence_score")),
        issue_key=str(data.get("issue_key", "") or ""),
        duplicate_of_issue_key=str(data.get("duplicate_of_issue_key", "") or ""),
        summary_ko=str(data.get("summary_ko", "") or ""),
        implication_ko=str(data.get("implication_ko", "") or ""),
        reason_ko=str(data.get("reason_ko", "") or ""),
        telegram_title_ko=str(data.get("telegram_title_ko", "") or ""),
        risk_flags=_flags(data.get("risk_flags")),
        raw_response=raw_response,
    )


class OpenRouterJudge:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def enabled(self) -> bool:
        return bool(self.settings.openrouter_api_key)

    def judge_relevance(self, item: Item, limiter: CallLimiter) -> Stage1Result:
        last_raw = ""
        for attempt in range(2):
            try:
                text, raw = self._chat(self.settings.stage1_model, self._stage1_messages(item), STAGE1_SCHEMA, limiter)
                data = _parse_json_object(text)
            except JSONDecodeError:
                last_raw = raw if "raw" in locals() else last_raw
                if attempt == 0:
                    continue
                return Stage1Result(True, "stage1 JSON parse failed; recall-first pass", ("stage1_json_parse_failed",), last_raw)
            relevant = bool(data.get("relevant", True))
            reason = str(data.get("reason", "") or "")
            return Stage1Result(relevant, reason, (), raw)
        return Stage1Result(True, "stage1 JSON parse failed; recall-first pass", ("stage1_json_parse_failed",), last_raw)

    def judge_article(
        self,
        item: Item,
        stage1: Stage1Result,
        recent_history: list[JsonObject],
        criteria_text: str,
        limiter: CallLimiter,
    ) -> Stage2Result:
        last_raw = ""
        for attempt in range(2):
            try:
                text, raw = self._chat(
                    self.settings.stage2_model,
                    self._stage2_messages(item, stage1, recent_history, criteria_text),
                    JUDGMENT_SCHEMA,
                    limiter,
                )
                return judgment_from_data(_parse_json_object(text), raw)
            except JSONDecodeError:
                last_raw = raw if "raw" in locals() else last_raw
                if attempt == 0:
                    continue
                return Stage2Failure("stage2 JSON parse failed", last_raw, ("stage2_json_parse_failed",))
        return Stage2Failure("stage2 JSON parse failed", last_raw, ("stage2_json_parse_failed",))

    def should_send(self, stage1: Stage1Result, stage2: Stage2Result) -> tuple[bool, str]:
        if not stage1.relevant:
            return False, "stage1_irrelevant"
        match stage2:
            case Stage2Failure(reason=reason):
                return False, reason
            case ArticleJudgment(duplicate_of_issue_key=duplicate, novelty_score=novelty):
                if duplicate and novelty < 4:
                    return False, "duplicate_without_major_update"
                return True, "recall_first_send"
            case unreachable:
                assert_never(unreachable)

    def _chat(
        self,
        model: str,
        messages: list[JsonObject],
        schema: JsonObject,
        limiter: CallLimiter,
    ) -> tuple[str, str]:
        limiter.claim()
        payload: JsonObject = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "news_radar", "strict": True, "schema": schema},
            },
        }
        try:
            response = post_json(
                OPENROUTER_URL,
                payload,
                headers={"Authorization": f"Bearer {self.settings.openrouter_api_key}"},
                timeout=60,
            )
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenRouter API error {exc.code}: {detail}") from exc
        raw_response = json.dumps(response, ensure_ascii=False)
        return _message_content(response), raw_response

    def _stage1_messages(self, item: Item) -> list[JsonObject]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a recall-first relevance filter for Korean food, beverage, cosmetics, "
                    "K-beauty, and K-food investment news. Return only JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Mark relevant=true if the item could be related to Korean food, beverage, cosmetics, "
                    "K-beauty, Korean skincare, Korean cosmetics, K-food, Korean snacks, Korean beverages, "
                    "or Korean ramen. Only mark false when it is clearly unrelated.\n\n"
                    f"Item:\n{json.dumps(item_payload(item), ensure_ascii=False)}"
                ),
            },
        ]

    def _stage2_messages(
        self,
        item: Item,
        stage1: Stage1Result,
        recent_history: list[JsonObject],
        criteria_text: str,
    ) -> list[JsonObject]:
        payload: JsonObject = {
            "item": {
                "source": item.source,
                "stream": item.stream,
                "title": item.title,
                "description": item.description,
                "url": item.url,
                "published_at": item.published_at,
            },
            "stage1": {
                "relevant": stage1.relevant,
                "reason": stage1.reason,
                "risk_flags": list(stage1.risk_flags),
            },
            "recent_history": recent_history,
        }
        return [
            {
                "role": "system",
                "content": (
                    "You write Korean investment alert judgments for a food, beverage, and cosmetics "
                    "Telegram room. Follow the criteria exactly and return one JSON object."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"판정 기준 전문:\n{criteria_text}\n\n"
                    "출력은 JUDGMENT_SCHEMA와 같은 JSON object 하나만 반환하라. "
                    "중요도가 낮아도 한국 음식료/화장품 산업과 조금이라도 관련 있으면 요약을 만든다. "
                    "최근 이력과 같은 이슈이면 duplicate_of_issue_key를 채우고 novelty_score를 낮게 준다.\n\n"
                    f"입력:\n{json.dumps(payload, ensure_ascii=False)}"
                ),
            },
        ]


def item_payload(item: Item) -> JsonObject:
    return {
        "source": item.source,
        "stream": item.stream,
        "title": item.title,
        "description": item.description,
        "url": item.url,
        "published_at": item.published_at,
    }

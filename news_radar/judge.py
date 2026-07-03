from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Final, assert_never

from .config import Settings
from .json_helpers import JsonShapeError, list_or_empty, parse_json_object
from .models import ArticleJudgment, Item, JsonObject, JsonValue, Stage1Result, Stage2Failure, Stage2Result
from .openrouter import message_content, post_openrouter
from .schemas import JUDGMENT_SCHEMA, STAGE1_SCHEMA


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


@dataclass(frozen=True, slots=True)
class ChatJsonResult:
    data: JsonObject | None
    raw_response: str


def _clamp_score(value: JsonValue) -> int:
    if isinstance(value, bool) or value is None:
        return 1
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(5, score))


def _flags(value: JsonValue) -> tuple[str, ...]:
    return tuple(str(flag) for flag in list_or_empty(value) if str(flag).strip())


def judgment_from_data(data: JsonObject, raw_response: str) -> ArticleJudgment:
    return ArticleJudgment(
        keep=bool(data.get("keep", False)),
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

    def judge_relevance(self, item: Item, criteria_text: str, limiter: CallLimiter) -> Stage1Result:
        result = self._chat_json(
            self.settings.stage1_model,
            self._stage1_messages(item, criteria_text),
            STAGE1_SCHEMA,
            limiter,
        )
        if result.data is None:
            return Stage1Result(
                True,
                "stage1 JSON parse failed; recall-first pass",
                ("stage1_json_parse_failed",),
                result.raw_response,
            )
        relevant = bool(result.data.get("relevant", True))
        reason = str(result.data.get("reason", "") or "")
        return Stage1Result(relevant, reason, (), result.raw_response)

    def judge_article(
        self,
        item: Item,
        stage1: Stage1Result,
        recent_history: list[JsonObject],
        criteria_text: str,
        limiter: CallLimiter,
    ) -> Stage2Result:
        result = self._chat_json(
            self.settings.stage2_model,
            self._stage2_messages(item, stage1, recent_history, criteria_text),
            JUDGMENT_SCHEMA,
            limiter,
        )
        if result.data is None:
            return Stage2Failure("stage2 JSON parse failed", result.raw_response, ("stage2_json_parse_failed",))
        return judgment_from_data(result.data, result.raw_response)

    def should_send(self, stage1: Stage1Result, stage2: Stage2Result) -> tuple[bool, str]:
        if not stage1.relevant:
            return False, "stage1_irrelevant"
        match stage2:
            case Stage2Failure(reason=reason):
                return False, reason
            case ArticleJudgment(keep=False):
                return False, "criteria_excluded"
            case ArticleJudgment(duplicate_of_issue_key=duplicate, novelty_score=novelty) as judgment:
                if duplicate and novelty < 4:
                    return False, "duplicate_without_major_update"
                if judgment.importance_score < self.settings.min_send_importance:
                    return False, "below_send_tier"
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
        response = post_openrouter(self.settings.openrouter_api_key, payload, timeout=60)
        raw_response = json.dumps(response, ensure_ascii=False)
        return message_content(response), raw_response

    def _chat_json(
        self,
        model: str,
        messages: list[JsonObject],
        schema: JsonObject,
        limiter: CallLimiter,
    ) -> ChatJsonResult:
        last_raw = ""
        for attempt in range(2):
            text, raw_response = self._chat(model, messages, schema, limiter)
            last_raw = raw_response
            try:
                return ChatJsonResult(parse_json_object(text), raw_response)
            except (json.JSONDecodeError, JsonShapeError):
                if attempt == 0:
                    continue
        return ChatJsonResult(None, last_raw)

    def _stage1_messages(self, item: Item, criteria_text: str) -> list[JsonObject]:
        criteria = criteria_text.strip()
        if criteria:
            instruction = (
                f"판정 기준 전문:\n{criteria}\n\n"
                "Mark relevant=true if the item may match the criteria. "
                "Only mark false when it is clearly unrelated or explicitly excluded by the criteria."
            )
        else:
            instruction = (
                "Mark relevant=true if the item could be related to Korean food, beverage, cosmetics, "
                "K-beauty, Korean skincare, Korean cosmetics, K-food, Korean snacks, Korean beverages, "
                "or Korean ramen. Only mark false when it is clearly unrelated."
            )
        return [
            {
                "role": "system",
                "content": (
                    "You are a recall-first relevance filter for investment news. Return only JSON."
                ),
            },
            {
                "role": "user",
                "content": f"{instruction}\n\nItem:\n{json.dumps(item_payload(item), ensure_ascii=False)}",
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
            "item": item_payload(item),
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
                    "keep=false는 기준문서의 명시적 제외 범주(단순 제품 리뷰·뷰티 팁·한국과 무관한 일반 소비재)에 해당할 때만 사용한다. "
                    "불확실하면 keep=true로 둔다. "
                    "stream/회사명은 이 기사를 찾은 검색 키워드일 뿐, 기사의 주체라고 가정하지 말 것. "
                    "요약·투자포인트는 제공된 제목과 설명에 명시된 사실만 사용. 명시되지 않은 사건·주체 관계를 추론해 단정하지 말 것. "
                    "주체가 불명확하면 제목의 표현을 그대로 유지. "
                    "telegram_title_ko에도 동일 원칙을 적용하라. "
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

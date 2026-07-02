from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .config import Settings
from .http import post_json
from .models import ArticleJudgment, Item, JsonObject


KST = timezone(timedelta(hours=9))


class TelegramClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def enabled(self) -> bool:
        return bool(self.settings.send_telegram and self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    def send_judgment(self, row_id: int, item: Item, judgment: ArticleJudgment) -> None:
        text = format_message(item, judgment)
        if not self.enabled():
            print(f"[telegram:dry-run] row_id={row_id}\n{text}\n", flush=True)
            return
        payload: JsonObject = {
            "chat_id": self.settings.telegram_chat_id,
            "text": text,
            "disable_web_page_preview": False,
            "disable_notification": quiet_hours(),
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "👍 유용", "callback_data": f"fb:g:{row_id}"},
                        {"text": "👎 버림", "callback_data": f"fb:b:{row_id}"},
                    ]
                ]
            },
        }
        post_json(f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage", payload)


def quiet_hours() -> bool:
    hour = datetime.now(timezone.utc).astimezone(KST).hour
    return hour >= 23 or hour < 7


def importance_prefix(score: int) -> str:
    if score >= 4:
        return "⭐"
    if score == 3:
        return "●"
    return "○"


def format_message(item: Item, judgment: ArticleJudgment) -> str:
    title = judgment.telegram_title_ko or item.title
    summary = judgment.summary_ko or item.description[:220]
    implication = judgment.implication_ko or judgment.reason_ko
    return "\n".join(
        [
            f"{importance_prefix(judgment.importance_score)} {title}",
            "",
            f"요약: {summary}",
            f"투자포인트: {implication}",
            item.url,
        ]
    )


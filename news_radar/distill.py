from __future__ import annotations

import json

from .config import load_settings
from .console import configure_utf8_output
from .json_helpers import extract_fenced_text
from .models import JsonObject
from .openrouter import message_content, post_openrouter
from .store import SeenStore


def cap_lines(text: str, limit: int = 40) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    capped = "\n".join(lines[:limit]).strip()
    return f"{capped}\n" if capped else ""


def validation_error(text: str) -> str | None:
    lines = text.splitlines()
    meaningful_lines = [line for line in lines if line.strip()]
    headers = {line.strip() for line in lines if line.strip().startswith("#")}
    if len(meaningful_lines) < 10:
        return "criteria must contain at least 10 non-empty lines"
    if "# 해외" not in headers or "# 국내" not in headers:
        return "criteria must include # 해외 and # 국내 headers"
    return None


def validated_criteria_text(raw_text: str) -> str | None:
    candidate = cap_lines(extract_fenced_text(raw_text))
    if validation_error(candidate) is not None:
        return None
    return candidate


def main() -> None:
    configure_utf8_output()
    settings = load_settings()
    if not settings.openrouter_api_key:
        print("[distill:skip] OPENROUTER_API_KEY missing", flush=True)
        return
    store = SeenStore(settings.data_dir / "monitor.sqlite3")
    try:
        rows = store.get_distill_rows(7)
    finally:
        store.close()
    current = settings.criteria_file.read_text(encoding="utf-8")
    payload: JsonObject = {
        "model": settings.stage2_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Rewrite Korean alert criteria for a recall-first food, beverage, cosmetics news radar. "
                    "Keep it practical, under 40 lines, with separate overseas and domestic sections."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"현재 기준:\n{current}\n\n"
                    f"최근 7일 판정/피드백:\n{json.dumps(rows, ensure_ascii=False)}\n\n"
                    "피드백 라벨 의미: good=유용, bad=버림, "
                    "known=사용자가 이미 알고 있던 뉴스. 뉴스 유형은 유효하니 해당 범주를 제외하지 말고, "
                    "신선도·중복 판정을 엄격히 하는 근거로만 사용.\n\n"
                    "기준 문서만 한국어로 출력하라."
                ),
            },
        ],
        "temperature": 0.2,
    }
    response = post_openrouter(settings.openrouter_api_key, payload, timeout=60)
    next_text = validated_criteria_text(message_content(response))
    if next_text is None:
        print("[distill:rejected] criteria validation failed", flush=True)
        return
    settings.criteria_file.write_text(next_text, encoding="utf-8")
    print(f"[distill:done] rows={len(rows)} file={settings.criteria_file}", flush=True)


if __name__ == "__main__":
    main()

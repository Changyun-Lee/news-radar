from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3

from .models import Item, JudgmentRecord, JsonObject, Source


class SeenStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_items (
                    source TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL,
                    stream TEXT NOT NULL,
                    title TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    notified_at TEXT,
                    PRIMARY KEY (source, dedupe_key)
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS judgments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL,
                    stream TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    url TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    judged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    stage1_relevant INTEGER NOT NULL,
                    stage1_reason TEXT NOT NULL,
                    stage1_model TEXT NOT NULL,
                    stage2_model TEXT NOT NULL,
                    raw_response TEXT NOT NULL,
                    importance_score INTEGER NOT NULL,
                    novelty_score INTEGER NOT NULL,
                    confidence_score INTEGER NOT NULL,
                    issue_key TEXT NOT NULL,
                    duplicate_of_issue_key TEXT NOT NULL,
                    summary_ko TEXT NOT NULL,
                    implication_ko TEXT NOT NULL,
                    reason_ko TEXT NOT NULL,
                    telegram_title_ko TEXT NOT NULL,
                    risk_flags_json TEXT NOT NULL,
                    sent INTEGER NOT NULL DEFAULT 0,
                    sent_at TEXT,
                    decision TEXT NOT NULL,
                    UNIQUE(source, dedupe_key)
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    row_id INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS worker_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_judgments_stream_time ON judgments(stream, judged_at)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_row_id ON feedback(row_id)")

    def close(self) -> None:
        self.conn.close()

    def prune(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        if self.get_state("last_pruned") == today:
            return
        with self.conn:
            self.conn.execute("DELETE FROM seen_items WHERE first_seen_at < datetime('now', '-30 days')")
            self.conn.execute("DELETE FROM judgments WHERE judged_at < datetime('now', '-30 days')")
            self.conn.execute("DELETE FROM feedback WHERE at < datetime('now', '-90 days')")
            self.conn.execute(
                "INSERT INTO worker_state(key, value) VALUES('last_pruned', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (today,),
            )

    def is_first_run(self, source: Source) -> bool:
        row = self.conn.execute("SELECT value FROM worker_state WHERE key = ?", (f"initialized:{source}",)).fetchone()
        return row is None

    def mark_initialized(self, source: Source) -> None:
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO worker_state(key, value) VALUES(?, CURRENT_TIMESTAMP)", (f"initialized:{source}",))

    def get_state(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM worker_state WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def set_state(self, key: str, value: str) -> None:
        if self.get_state(key) == value:
            return
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO worker_state(key, value) VALUES(?, ?)", (key, value))

    def has_seen(self, item: Item) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_items WHERE source = ? AND dedupe_key = ?",
            (item.source, item.dedupe_key),
        ).fetchone()
        return row is not None

    def add_seen(self, item: Item) -> bool:
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT OR IGNORE INTO seen_items(source, dedupe_key, stream, title)
                VALUES (?, ?, ?, ?)
                """,
                (item.source, item.dedupe_key, item.stream, item.title),
            )
        return cursor.rowcount == 1

    def mark_notified(self, item: Item) -> None:
        with self.conn:
            self.conn.execute(
                """
                UPDATE seen_items
                SET notified_at = CURRENT_TIMESTAMP
                WHERE source = ? AND dedupe_key = ?
                """,
                (item.source, item.dedupe_key),
            )

    def record_judgment(self, record: JudgmentRecord) -> int:
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT OR REPLACE INTO judgments(
                    source, dedupe_key, stream, title, description, url, published_at,
                    stage1_relevant, stage1_reason, stage1_model, stage2_model, raw_response,
                    importance_score, novelty_score, confidence_score, issue_key,
                    duplicate_of_issue_key, summary_ko, implication_ko, reason_ko,
                    telegram_title_ko, risk_flags_json, decision
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.item.source,
                    record.item.dedupe_key,
                    record.item.stream,
                    record.item.title,
                    record.item.description,
                    record.item.url,
                    record.item.published_at,
                    int(record.stage1_relevant),
                    record.stage1_reason,
                    record.stage1_model,
                    record.stage2_model,
                    record.raw_response,
                    record.importance_score,
                    record.novelty_score,
                    record.confidence_score,
                    record.issue_key,
                    record.duplicate_of_issue_key,
                    record.summary_ko,
                    record.implication_ko,
                    record.reason_ko,
                    record.telegram_title_ko,
                    json.dumps(list(record.risk_flags), ensure_ascii=False),
                    record.decision,
                ),
            )
        return int(cursor.lastrowid)

    def mark_judgment_sent(self, row_id: int, decision: str) -> None:
        with self.conn:
            self.conn.execute(
                """
                UPDATE judgments
                SET sent = 1,
                    sent_at = CURRENT_TIMESTAMP,
                    decision = ?
                WHERE id = ?
                """,
                (decision, row_id),
            )

    def delete_judgment(self, row_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM judgments WHERE id = ?", (row_id,))

    def get_recent_history(self, source: Source, stream: str, days: int, limit: int) -> list[JsonObject]:
        rows = self.conn.execute(
            """
            SELECT judged_at, title, issue_key, summary_ko, decision, sent
            FROM judgments
            WHERE source = ?
              AND stream = ?
              AND judged_at >= datetime('now', ?)
            ORDER BY judged_at DESC
            LIMIT ?
            """,
            (source, stream, f"-{days} days", limit),
        ).fetchall()
        return [
            {
                "judged_at": str(row[0]),
                "title": str(row[1]),
                "issue_key": str(row[2]),
                "summary_ko": str(row[3]),
                "decision": str(row[4]),
                "sent": bool(row[5]),
            }
            for row in rows
        ]

    def add_feedback(self, row_id: int, label: str) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO feedback(row_id, label) VALUES(?, ?)", (row_id, label))

    def get_distill_rows(self, days: int) -> list[JsonObject]:
        rows = self.conn.execute(
            """
            SELECT j.id, j.source, j.stream, j.title, j.summary_ko, j.implication_ko,
                   j.importance_score, j.novelty_score, j.decision,
                   group_concat(f.label, ',') AS feedback_labels
            FROM judgments j
            LEFT JOIN feedback f ON f.row_id = j.id
            WHERE j.judged_at >= datetime('now', ?)
            GROUP BY j.id
            ORDER BY j.judged_at DESC
            LIMIT 80
            """,
            (f"-{days} days",),
        ).fetchall()
        return [
            {
                "id": int(row[0]),
                "source": str(row[1]),
                "stream": str(row[2]),
                "title": str(row[3]),
                "summary_ko": str(row[4]),
                "implication_ko": str(row[5]),
                "importance_score": int(row[6]),
                "novelty_score": int(row[7]),
                "decision": str(row[8]),
                "feedback": str(row[9] or ""),
            }
            for row in rows
        ]


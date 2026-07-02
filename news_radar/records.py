from __future__ import annotations

from typing import assert_never

from .config import Settings
from .models import ArticleJudgment, Item, JudgmentRecord, Stage1Result, Stage2Failure, Stage2Result


def skip_record(item: Item, decision: str, reason: str) -> JudgmentRecord:
    return JudgmentRecord(
        item=item,
        stage1_relevant=False,
        stage1_reason=reason,
        stage1_model="",
        stage2_model="",
        raw_response="{}",
        importance_score=0,
        novelty_score=0,
        confidence_score=0,
        issue_key="",
        duplicate_of_issue_key="",
        summary_ko="",
        implication_ko="",
        reason_ko=reason,
        telegram_title_ko="",
        risk_flags=(decision,),
        decision=decision,
    )


def stage1_record(settings: Settings, item: Item, stage1: Stage1Result, decision: str) -> JudgmentRecord:
    return JudgmentRecord(
        item=item,
        stage1_relevant=stage1.relevant,
        stage1_reason=stage1.reason,
        stage1_model=settings.stage1_model,
        stage2_model="",
        raw_response=stage1.raw_response,
        importance_score=0,
        novelty_score=0,
        confidence_score=0,
        issue_key="",
        duplicate_of_issue_key="",
        summary_ko="",
        implication_ko="",
        reason_ko=stage1.reason,
        telegram_title_ko="",
        risk_flags=stage1.risk_flags,
        decision=decision,
    )


def stage2_record(
    settings: Settings,
    item: Item,
    stage1: Stage1Result,
    stage2: Stage2Result,
    decision: str,
) -> JudgmentRecord:
    match stage2:
        case Stage2Failure(reason=reason, raw_response=raw_response, risk_flags=risk_flags):
            return JudgmentRecord(
                item=item,
                stage1_relevant=stage1.relevant,
                stage1_reason=stage1.reason,
                stage1_model=settings.stage1_model,
                stage2_model=settings.stage2_model,
                raw_response=raw_response,
                importance_score=0,
                novelty_score=0,
                confidence_score=0,
                issue_key="",
                duplicate_of_issue_key="",
                summary_ko="",
                implication_ko="",
                reason_ko=reason,
                telegram_title_ko="",
                risk_flags=(*stage1.risk_flags, *risk_flags),
                decision=decision,
            )
        case ArticleJudgment() as judgment:
            return JudgmentRecord(
                item=item,
                stage1_relevant=stage1.relevant,
                stage1_reason=stage1.reason,
                stage1_model=settings.stage1_model,
                stage2_model=settings.stage2_model,
                raw_response=judgment.raw_response,
                importance_score=judgment.importance_score,
                novelty_score=judgment.novelty_score,
                confidence_score=judgment.confidence_score,
                issue_key=judgment.issue_key,
                duplicate_of_issue_key=judgment.duplicate_of_issue_key,
                summary_ko=judgment.summary_ko,
                implication_ko=judgment.implication_ko,
                reason_ko=judgment.reason_ko,
                telegram_title_ko=judgment.telegram_title_ko,
                risk_flags=(*stage1.risk_flags, *judgment.risk_flags),
                decision=decision,
            )
        case unreachable:
            assert_never(unreachable)


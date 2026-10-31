"""How much text one account keeps in the database, counted by the database
itself (AGENTS.md §7 Repository), so nothing is loaded to measure it."""

from __future__ import annotations

from sqlalchemy import Text, cast, func, select
from sqlalchemy.orm import Session

from api.models import Pipeline, PipelineStep, Run, RunStep, User


def text_characters(session: Session, user: User) -> int:
    """Characters in the account's runs, run steps and pipeline prompts: what grows
    with no per-account bound, and what a copy of the account is mostly made of."""
    runs = select(Run.id).where(Run.user_id == user.id)
    pipelines = select(Pipeline.id).where(Pipeline.user_id == user.id)
    measures = (
        select(
            func.sum(
                func.length(Run.input_text)
                + func.length(Run.final_output)
                + func.length(cast(Run.definition, Text))
            )
        ).where(Run.user_id == user.id),
        select(func.sum(func.length(RunStep.input_used) + func.length(RunStep.output))).where(
            RunStep.run_id.in_(runs)
        ),
        select(func.sum(func.length(PipelineStep.prompt))).where(
            PipelineStep.pipeline_id.in_(pipelines)
        ),
    )
    return sum(session.scalar(measure) or 0 for measure in measures)

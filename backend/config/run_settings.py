"""Settings of pipeline runs: parallelism, background execution, budgets, schedules."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from config.fields import EmptyIsNone

#: A spending limit in USD; empty in the environment is none.
CostLimit = Annotated[float | None, EmptyIsNone, Field(gt=0, allow_inf_nan=False)]
#: A limit on tokens (in and out); empty in the environment is none.
TokenLimit = Annotated[int | None, EmptyIsNone, Field(ge=1)]


class RunSettings(BaseModel):
    # Upper bound on provider calls one pipeline run makes at once for a stage
    # whose steps run in parallel.
    pipeline_max_parallel_steps: int = Field(
        4, ge=1, validation_alias="PIPELINE_MAX_PARALLEL_STEPS"
    )
    # --- Background runs (api/services/runs.py) -------------------------------
    # Runs executing at once in this process; the others wait, queued.
    run_max_concurrent: int = Field(4, ge=1, validation_alias="RUN_MAX_CONCURRENT")
    # Runs one account may have queued, running or waiting at once, whatever starts
    # them; below RUN_MAX_CONCURRENT, one account cannot take every slot.
    run_max_active_per_user: int = Field(3, ge=1, validation_alias="RUN_MAX_ACTIVE_PER_USER")
    # How long POST /pipelines/{id}/run (and chat's run_pipeline) waits for a run's
    # end before answering that it goes on in the background.
    run_wait_max_seconds: float = Field(300.0, gt=0, validation_alias="RUN_WAIT_MAX_SECONDS")
    # On shutdown, how long active runs get to record that they were interrupted.
    run_shutdown_grace_seconds: float = Field(
        5.0, gt=0, validation_alias="RUN_SHUTDOWN_GRACE_SECONDS"
    )
    # --- Spending limits (api/services/run_budget.py); empty is none ------------
    # The limits of a run whose starter sets none. A model with no known price
    # never reaches a cost limit: only a token limit bounds it.
    run_default_max_cost_usd: CostLimit = Field(None, validation_alias="RUN_DEFAULT_MAX_COST_USD")
    run_default_max_tokens: TokenLimit = Field(None, validation_alias="RUN_DEFAULT_MAX_TOKENS")
    # Ceilings no run may pass: a limit asked for above one is refused, and a
    # default (or a limit saved before the ceiling was lowered) is cut to it.
    run_max_cost_usd: CostLimit = Field(None, validation_alias="RUN_MAX_COST_USD")
    run_max_tokens: TokenLimit = Field(None, validation_alias="RUN_MAX_TOKENS")
    # --- Scheduled runs (api/services/schedules) -------------------------------
    # The scheduler runs inside the API process; false keeps every schedule
    # saved but starts none (e.g. in a second process: only one may schedule).
    scheduler_enabled: bool = Field(True, validation_alias="SCHEDULER_ENABLED")
    # How often it looks for schedules that are due, so a run starts at most
    # this late.
    scheduler_tick_seconds: float = Field(30.0, gt=0, validation_alias="SCHEDULER_TICK_SECONDS")
    schedules_max_per_user: int = Field(20, ge=0, validation_alias="SCHEDULES_MAX_PER_USER")

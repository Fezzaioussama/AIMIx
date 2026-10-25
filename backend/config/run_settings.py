"""Settings of pipeline runs: parallelism, background execution, budgets, schedules."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class RunSettings(BaseModel):
    # Upper bound on provider calls one pipeline run makes at once for a stage
    # whose steps run in parallel.
    pipeline_max_parallel_steps: int = Field(
        4, ge=1, validation_alias="PIPELINE_MAX_PARALLEL_STEPS"
    )
    # --- Background runs (api/services/runs.py) -------------------------------
    # Runs executing at once in this process; the others wait, queued.
    run_max_concurrent: int = Field(4, ge=1, validation_alias="RUN_MAX_CONCURRENT")
    # On shutdown, how long active runs get to record that they were interrupted.
    run_shutdown_grace_seconds: float = Field(
        5.0, gt=0, validation_alias="RUN_SHUTDOWN_GRACE_SECONDS"
    )
    # A run stops once its model calls cost this much (USD), unless the person
    # starting it sets their own limit. Empty (None): no limit.
    run_default_max_cost_usd: float | None = Field(
        None, gt=0, allow_inf_nan=False, validation_alias="RUN_DEFAULT_MAX_COST_USD"
    )
    # --- Scheduled runs (api/services/schedules) -------------------------------
    # The scheduler runs inside the API process; false keeps every schedule
    # saved but starts none (e.g. in a second process: only one may schedule).
    scheduler_enabled: bool = Field(True, validation_alias="SCHEDULER_ENABLED")
    # How often it looks for schedules that are due, so a run starts at most
    # this late.
    scheduler_tick_seconds: float = Field(30.0, gt=0, validation_alias="SCHEDULER_TICK_SECONDS")
    schedules_max_per_user: int = Field(20, ge=0, validation_alias="SCHEDULES_MAX_PER_USER")

    @field_validator("run_default_max_cost_usd", mode="before")
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        """``RUN_DEFAULT_MAX_COST_USD=`` (empty) means no limit."""
        return None if isinstance(value, str) and not value.strip() else value

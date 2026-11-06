"""The step agent a run gets when nobody is signed in: a schedule's run, a webhook
call's, or a run resumed at startup. Built as a request of the owner's builds one
(``api/deps.pipeline_agent_factory``): their LLM profile, from the Settings page or
else the environment, and a ``PipelineAgentGenerator``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from api.db import Database
from api.models import User
from api.security import SecretBox
from api.services import llm_settings
from api.services.llm import provider_config
from api.services.multiagent.contracts import StepAgent
from api.services.multiagent.step_agent import PipelineAgentGenerator


class OwnerAgents(Protocol):
    """Builds the step agent an owner's run uses, without a request of theirs."""

    def __call__(self, session: Session, owner: User) -> StepAgent: ...


@dataclass(frozen=True)
class ProfileAgents:
    """An owner's step agent from their LLM profile (the Settings page, else the
    environment): the run spends their key."""

    database: Database
    box: SecretBox

    def __call__(self, session: Session, owner: User) -> StepAgent:
        profile = llm_settings.resolve_profile(session, owner, self.box)
        # Fail fast (§6): with no key at all the run could only fail, so the
        # caller reports it (on the schedule, to the webhook's caller, on the
        # run left interrupted) instead of starting a run that cannot work.
        provider_config(profile)
        return PipelineAgentGenerator(self.database, owner, profile)

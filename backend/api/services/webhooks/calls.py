"""Calls of a webhook by another app (``POST /hooks/<token>``, public): find it by its
token, check its allowance, and start a run of its pipeline as its owner, the way a
schedule does (``owner_agents.ProfileAgents``)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from api.db import Database
from api.exceptions import DomainError, NotFound
from api.models import Webhook
from api.repositories import webhooks as repository
from api.services.owner_agents import OwnerAgents
from api.services.rate_limits import RateLimitRequest, enforce
from api.services.run_recorder import utcnow
from api.services.runs import RunService
from api.services.webhooks.inputs import call_start
from api.services.webhooks.service import token_hash

logger = logging.getLogger(__name__)

#: The rate-limit bucket a webhook's calls count against.
CALL_ACTION = "webhook:call"


@dataclass(frozen=True)
class CallPolicy:
    """How often one webhook may start runs (WEBHOOK_RATE_LIMIT_*), and the key the
    rate-limit table hashes identities with."""

    secret_key: str
    max_calls: int
    window_seconds: int


class WebhookCalls:
    """Starts the run a webhook call asks for; the run's id."""

    def __init__(
        self, database: Database, runs: RunService, agents: OwnerAgents, policy: CallPolicy
    ) -> None:
        self._database = database
        self._runs = runs
        self._agents = agents
        self._policy = policy

    def trigger(self, token: str, body: bytes) -> int:
        """Start a run of the token's pipeline with what ``body`` gives it.

        An unknown token and a switched-off webhook are the same ``NotFound``. A call
        past the allowance is ``Throttled``; any other refusal (inputs the pipeline
        does not take, no key, too many runs) is kept as the webhook's ``last_error``."""
        with self._database.session() as session:
            webhook = repository.by_token_hash(session, token_hash(token))
            if webhook is None or not webhook.enabled:
                raise NotFound("No webhook answers at this address.")
            enforce(session, self._policy.secret_key, self._allowance(webhook))
            try:
                run_id = self._start(session, webhook, body)
            except DomainError as cause:
                repository.record_call(session, webhook, utcnow(), cause.detail)
                logger.info("webhook.refused webhook_id=%s error=%s", webhook.id, cause.code)
                raise
            repository.record_call(session, webhook, utcnow(), "")
        logger.info("webhook.called webhook_id=%s run_id=%s", webhook.id, run_id)
        return run_id

    def _allowance(self, webhook: Webhook) -> RateLimitRequest:
        limit = self._policy.max_calls
        return RateLimitRequest(
            f"webhook:{webhook.id}",
            CALL_ACTION,
            limit,
            self._policy.window_seconds,
            f"This webhook may start {limit} runs per {self._policy.window_seconds} seconds.",
        )

    def _start(self, session: Session, webhook: Webhook, body: bytes) -> int:
        pipeline = webhook.pipeline
        start = call_start(pipeline.inputs, body)
        agent = self._agents(session, pipeline.user)
        return self._runs.start(pipeline.user, pipeline, start, agent).run.id

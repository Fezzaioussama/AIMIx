"""What the chat's tool modules share (AGENTS.md §3): a refusal the agent can explain,
the account in a tool's own session, and the one way a tool saves a pipeline, checked
like the pipeline endpoints' saves."""

from __future__ import annotations

from langchain_core.tools import ToolException
from sqlalchemy.orm import Session

from api.models import Pipeline, User
from api.repositories import pipelines as repository
from api.schemas.pipelines import PipelineIn, PipelinePatch
from api.services import pipelines as pipeline_service
from api.services.files.disk import disk_reserve
from config.settings import get_settings


def refused(cause: Exception) -> ToolException:
    """A refused write reaches the agent as a tool error it can explain."""
    return ToolException(str(cause))


def session_user(session: Session, user: User) -> User:
    """The same account in the tool's own session, so a write can attach it."""
    owner = session.get(User, user.id)
    if owner is None:
        raise ToolException("Your account is no longer available.")
    return owner


def save_new(session: Session, user: User, body: PipelineIn) -> Pipeline:
    """Save ``body`` as a new pipeline of ``user``'s, as POST /pipelines does."""
    disk_reserve(get_settings()).ensure_room()
    owner = session_user(session, user)
    return repository.create_with_steps(session, owner, pipeline_service.body_changes(body))


def save_patch(session: Session, user: User, pipeline_id: int, body: PipelinePatch) -> Pipeline:
    """Apply ``body`` to one of ``user``'s pipelines, as PATCH /pipelines/<id> does."""
    disk_reserve(get_settings()).ensure_room()
    pipeline = repository.get_owned(session, session_user(session, user), pipeline_id)
    changes = pipeline_service.body_changes(body, pipeline)
    return repository.replace_steps(session, pipeline, changes)

"""FastAPI dependencies: the HTTP boundary's access to the database, settings,
the signed-in user, their LLM profile and provider (§5 D — tests override these)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from api.exceptions import NotAuthenticated
from api.models import User
from api.security import SecretBox, TokenSigner
from api.services import accounts, llm_settings
from api.services.agent import get_chat_agent
from api.services.chat import ChatAgent
from api.services.llm import LLMProfile, get_provider
from api.services.multiagent.contracts import StepAgent
from api.services.multiagent.step_agent import PipelineAgentGenerator
from api.services.tool_catalog import PipelineToolCatalog
from config.settings import Settings, get_settings
from llm.base import LLMProvider


def db_session(request: Request) -> Iterator[Session]:
    yield from request.app.state.database.sessions()


def app_settings() -> Settings:
    return get_settings()


DbSession = Annotated[Session, Depends(db_session)]
AppSettings = Annotated[Settings, Depends(app_settings)]


def token_signer(settings: AppSettings) -> TokenSigner:
    return TokenSigner(
        secret_key=settings.secret_key,
        access_lifetime=timedelta(minutes=settings.jwt_access_minutes),
        refresh_lifetime=timedelta(days=settings.jwt_refresh_days),
    )


Signer = Annotated[TokenSigner, Depends(token_signer)]

_bearer = HTTPBearer(auto_error=False)


def current_user(
    session: DbSession,
    signer: Signer,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """The account behind the request's bearer token, or a 401."""
    if credentials is None:
        raise NotAuthenticated("Authentication credentials were not provided.")
    return accounts.authenticate(session, signer, credentials.credentials)


CurrentUser = Annotated[User, Depends(current_user)]


def secret_box(settings: AppSettings) -> SecretBox:
    return SecretBox(settings.secret_key)


Secrets = Annotated[SecretBox, Depends(secret_box)]


def llm_profile(user: CurrentUser, session: DbSession, box: Secrets) -> LLMProfile:
    """The signed-in user's provider, default model and key (Settings page)."""
    return llm_settings.resolve_profile(session, user, box)


Profile = Annotated[LLMProfile, Depends(llm_profile)]

ProviderFactory = Callable[[], LLMProvider]


def provider_factory(profile: Profile) -> ProviderFactory:
    """Hands endpoints the factory, not the provider, so the request body is
    validated before an unconfigured provider can fail the request."""
    return partial(get_provider, profile)


Providers = Annotated[ProviderFactory, Depends(provider_factory)]


PipelineAgentFactory = Callable[[], StepAgent]


def pipeline_agent_factory(
    request: Request, user: CurrentUser, profile: Profile
) -> PipelineAgentFactory:
    """Bind pipeline agents to the request's authenticated user and their profile."""
    return partial(PipelineAgentGenerator, request.app.state.database, user, profile)


PipelineAgents = Annotated[PipelineAgentFactory, Depends(pipeline_agent_factory)]


def pipeline_tool_catalog(request: Request, user: CurrentUser) -> PipelineToolCatalog:
    return PipelineToolCatalog(request.app.state.database, user)


ToolCatalog = Annotated[PipelineToolCatalog, Depends(pipeline_tool_catalog)]


@dataclass(frozen=True)
class PipelineRunContext:
    user: User
    session: Session
    agents: PipelineAgentFactory


def pipeline_run_context(
    user: CurrentUser, session: DbSession, agents: PipelineAgents
) -> PipelineRunContext:
    return PipelineRunContext(user, session, agents)


PipelineRun = Annotated[PipelineRunContext, Depends(pipeline_run_context)]


AgentFactory = Callable[[], ChatAgent]


def agent_factory(
    request: Request, user: CurrentUser, profile: Profile, pipeline_agents: PipelineAgents
) -> AgentFactory:
    """Defer agent construction until after the chat request is validated."""
    return partial(get_chat_agent, request.app.state.database, user, profile, pipeline_agents)


Agents = Annotated[AgentFactory, Depends(agent_factory)]

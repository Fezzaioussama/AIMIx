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
from api.services.documents.contracts import ExtractionLimits
from api.services.documents.extraction import extraction_limits
from api.services.files.service import UploadPolicy
from api.services.files.storage import WorkspaceStorage, user_workspace_dir
from api.services.llm import LLMProfile, get_provider
from api.services.multiagent.contracts import StepAgent
from api.services.multiagent.step_agent import PipelineAgentGenerator
from api.services.rate_limits import RateLimitRequest, enforce
from api.services.tool_catalog import PipelineToolCatalog
from config.settings import Settings, get_settings
from llm.base import LLMProvider


def db_session(request: Request) -> Iterator[Session]:
    yield from request.app.state.database.sessions()


def app_settings() -> Settings:
    return get_settings()


DbSession = Annotated[Session, Depends(db_session)]
AppSettings = Annotated[Settings, Depends(app_settings)]


def auth_rate_limit(request: Request, session: DbSession, settings: AppSettings) -> None:
    """Persist one counter per client and auth path, shared by every app process."""
    identity = request.client.host if request.client else "unknown"
    enforce(
        session,
        settings.secret_key,
        RateLimitRequest(
            identity,
            request.url.path,
            settings.auth_rate_limit_requests,
            settings.auth_rate_limit_window_seconds,
        ),
    )


def document_limits(settings: AppSettings) -> ExtractionLimits:
    """What one document extraction may cost, from settings."""
    return extraction_limits(settings)


DocumentLimits = Annotated[ExtractionLimits, Depends(document_limits)]


def token_signer(settings: AppSettings) -> TokenSigner:
    return TokenSigner(
        secret_key=settings.secret_key,
        access_lifetime=timedelta(minutes=settings.jwt_access_minutes),
        refresh_lifetime=timedelta(days=settings.jwt_refresh_days),
    )


Signer = Annotated[TokenSigner, Depends(token_signer)]


@dataclass(frozen=True)
class AuthFlow:
    session: Session
    signer: TokenSigner
    settings: Settings


def auth_flow(session: DbSession, signer: Signer, settings: AppSettings) -> AuthFlow:
    return AuthFlow(session, signer, settings)


Auth = Annotated[AuthFlow, Depends(auth_flow)]

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


def user_files(user: CurrentUser, settings: AppSettings) -> WorkspaceStorage:
    """The signed-in user's private directory, the one their agents use too."""
    directory = user_workspace_dir(settings.workspace_dir, user.id)
    return WorkspaceStorage(directory, settings.workspace_max_total_bytes)


UserFiles = Annotated[WorkspaceStorage, Depends(user_files)]


def upload_policy(settings: AppSettings) -> UploadPolicy:
    """What the Files page accepts. DOCUMENT_MAX_BYTES caps every uploaded file,
    so the request size guard (``max_request_bytes``) bounds this upload too."""
    return UploadPolicy(
        max_file_bytes=settings.document_max_bytes,
        allowed_extensions=frozenset(settings.workspace_upload_extensions),
    )


FileUploads = Annotated[UploadPolicy, Depends(upload_policy)]


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

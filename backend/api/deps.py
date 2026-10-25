"""FastAPI dependencies: the HTTP boundary's access to the database, settings,
the signed-in user, their LLM profile and provider (§5 D — tests override these)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from api.exceptions import NotAuthenticated
from api.models import User
from api.security import SecretBox, TokenSigner
from api.services import accounts, llm_settings
from api.services.addresses import Resolver, resolve_host
from api.services.agent import get_chat_agent
from api.services.chat import ChatAgent
from api.services.documents.contracts import ExtractionLimits, OcrEngine
from api.services.documents.extraction import extraction_limits
from api.services.files.service import UploadPolicy
from api.services.files.storage import WorkspaceStorage, user_workspace_dir
from api.services.integrations.rules import IntegrationRules, rules_from
from api.services.integrations.service import IntegrationAccess
from api.services.llm import LLMProfile, get_provider
from api.services.multiagent.contracts import StepAgent
from api.services.multiagent.step_agent import PipelineAgentGenerator
from api.services.rate_limits import RateLimitRequest, enforce
from api.services.run_executor import RunExecutor
from api.services.run_recorder import utcnow
from api.services.runs import RunService, launcher
from api.services.schedules.service import ScheduleAccess
from api.services.templates.use import StepDefaults
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


def document_ocr(request: Request) -> OcrEngine | None:
    """The OCR engine the app built at startup; None when OCR is off or not installed."""
    engine: OcrEngine | None = request.app.state.ocr
    return engine


DocumentOcr = Annotated[OcrEngine | None, Depends(document_ocr)]


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


def run_executor(request: Request) -> RunExecutor:
    """Where runs execute: the app's background executor (tests swap it)."""
    executor: RunExecutor = request.app.state.run_executor
    return executor


Executor = Annotated[RunExecutor, Depends(run_executor)]


def run_service(request: Request, executor: Executor, settings: AppSettings) -> RunService:
    return RunService(request.app.state.database, executor, settings.pipeline_max_parallel_steps)


Runs = Annotated[RunService, Depends(run_service)]


@dataclass(frozen=True)
class PipelineRunContext:
    user: User
    session: Session
    agents: PipelineAgentFactory
    runs: RunService


def pipeline_run_context(
    user: CurrentUser, session: DbSession, agents: PipelineAgents, service: Runs
) -> PipelineRunContext:
    return PipelineRunContext(user, session, agents, service)


PipelineRun = Annotated[PipelineRunContext, Depends(pipeline_run_context)]


@dataclass(frozen=True)
class TemplateUseContext:
    user: User
    session: Session
    defaults: StepDefaults


def template_use_context(
    user: CurrentUser, session: DbSession, profile: Profile, catalog: ToolCatalog
) -> TemplateUseContext:
    """Who a template's pipeline is for, and the models and tools its steps may
    use. Tool discovery stays lazy: the service runs it once the slug is known."""
    return TemplateUseContext(user, session, StepDefaults(profile.models, catalog.available_sync))


TemplateUse = Annotated[TemplateUseContext, Depends(template_use_context)]


AgentFactory = Callable[[], ChatAgent]


def agent_factory(
    request: Request, user: CurrentUser, profile: Profile, context: PipelineRun
) -> AgentFactory:
    """Defer agent construction until after the chat request is validated. Its
    run_pipeline tool records runs like the Runs screen does."""
    launch = launcher(context.runs, user, context.agents)
    return partial(get_chat_agent, request.app.state.database, user, profile, launch)


Agents = Annotated[AgentFactory, Depends(agent_factory)]


def host_resolver() -> Resolver:
    """How the integration address checks resolve host names; tests swap in a fake."""
    return resolve_host


def integration_rules(
    settings: AppSettings, resolver: Annotated[Resolver, Depends(host_resolver)]
) -> IntegrationRules:
    return rules_from(settings, resolver)


def integration_access(
    user: CurrentUser,
    session: DbSession,
    box: Secrets,
    rules: Annotated[IntegrationRules, Depends(integration_rules)],
) -> IntegrationAccess:
    """The signed-in user's integrations (Settings → Integrations)."""
    return IntegrationAccess(session, user, box, rules)


Integrations = Annotated[IntegrationAccess, Depends(integration_access)]


def current_time() -> datetime:
    """The request's "now", in UTC; tests fix it."""
    return utcnow()


Now = Annotated[datetime, Depends(current_time)]


def schedule_access(
    user: CurrentUser, session: DbSession, settings: AppSettings, now: Now
) -> ScheduleAccess:
    """The signed-in user's schedules (the builder's Schedule panel, Runs screen)."""
    return ScheduleAccess(session, user, settings.schedules_max_per_user, now)


Schedules = Annotated[ScheduleAccess, Depends(schedule_access)]

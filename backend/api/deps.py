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
from api.models import UsageKind, User
from api.security import SecretBox, TokenSigner, secret_box_for
from api.services import accounts, llm_settings, run_feedback, user_memory
from api.services.account_data import workspace_of
from api.services.account_usage import account_meter, calls_of
from api.services.agent import get_chat_agent
from api.services.chat import ChatAgent
from api.services.chat_memory import ChatMemory, MemoryLimits
from api.services.chat_tools.scope import ChatScope
from api.services.chats import ChatAccess
from api.services.files.disk import disk_reserve
from api.services.files.service import UploadPolicy
from api.services.files.storage import WorkspaceStorage
from api.services.llm import LLMProfile, get_planner_provider, get_transcriber, planner_metering
from api.services.multiagent.contracts import StepAgent
from api.services.multiagent.step_agent import PipelineAgentGenerator
from api.services.run_executor import RunExecutor
from api.services.run_feedback import Lesson
from api.services.run_policy import run_policy
from api.services.run_recorder import utcnow
from api.services.runs import RunService
from api.services.schedules.service import ScheduleAccess
from api.services.templates.use import StepDefaults
from api.services.tool_catalog import PipelineToolCatalog
from config.settings import Settings, get_settings
from llm.base import LLMProvider
from llm.speech import PROVIDER as SPEECH_PROVIDER
from llm.speech import Transcriber
from llm.usage import UsageMeter


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
        fallback_keys=tuple(settings.secret_key_fallbacks),
        reset_lifetime=timedelta(minutes=settings.password_reset_minutes),
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
    return workspace_of(settings, user.id)


UserFiles = Annotated[WorkspaceStorage, Depends(user_files)]


def disk_room(settings: AppSettings) -> None:
    """Refuse a request that saves a pipeline while the disk the database shares
    with every account's files is nearly full (507). Add it to the route's
    ``dependencies``; runs and files check the same reserve themselves."""
    disk_reserve(settings).ensure_room()


@dataclass(frozen=True)
class AccountAccess:
    """The signed-in account, with what its own data lives in."""

    user: User
    session: Session
    files: WorkspaceStorage
    settings: Settings


def account_access(
    user: CurrentUser, session: DbSession, files: UserFiles, settings: AppSettings
) -> AccountAccess:
    return AccountAccess(user, session, files, settings)


Account = Annotated[AccountAccess, Depends(account_access)]


def upload_policy(settings: AppSettings) -> UploadPolicy:
    """What the Files page accepts. DOCUMENT_MAX_BYTES caps every uploaded file,
    so the request size guard (``max_request_bytes``) bounds this upload too."""
    return UploadPolicy(
        max_file_bytes=settings.document_max_bytes,
        allowed_extensions=frozenset(settings.workspace_upload_extensions),
    )


FileUploads = Annotated[UploadPolicy, Depends(upload_policy)]


def secret_box(settings: AppSettings) -> SecretBox:
    return secret_box_for(settings)


Secrets = Annotated[SecretBox, Depends(secret_box)]


def llm_profile(user: CurrentUser, session: DbSession, box: Secrets) -> LLMProfile:
    """The signed-in user's provider, default model and key (Settings page)."""
    return llm_settings.resolve_profile(session, user, box)


Profile = Annotated[LLMProfile, Depends(llm_profile)]

ProviderFactory = Callable[[], LLMProvider]


def planner_meter(request: Request, user: CurrentUser, profile: Profile) -> UsageMeter:
    """Hears the planner's calls for the account: the day's allowance of the server's
    key, and the usage events (``account_usage``)."""
    calls = calls_of(UsageKind.PLANNER, profile.default_model)
    return account_meter(request.app.state.database, user.id, profile, calls)


PlannerMeter = Annotated[UsageMeter, Depends(planner_meter)]


def provider_factory(profile: Profile, meter: PlannerMeter) -> ProviderFactory:
    """The planner's provider, built only once the request body is valid."""
    return partial(get_planner_provider, profile, planner_metering(meter, profile))


Providers = Annotated[ProviderFactory, Depends(provider_factory)]

TranscriberFactory = Callable[[], Transcriber]


def voice_transcribers(user: CurrentUser, session: DbSession, box: Secrets) -> TranscriberFactory:
    """Speech to text on the user's Meta key, whichever provider they chose; built
    only once the clip is valid."""
    profile = llm_settings.provider_profile(session, user, box, SPEECH_PROVIDER)
    return partial(get_transcriber, profile)


Transcribers = Annotated[TranscriberFactory, Depends(voice_transcribers)]


def voice_max_bytes(settings: AppSettings) -> int:
    return settings.voice_max_bytes


VoiceMaxBytes = Annotated[int, Depends(voice_max_bytes)]


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
class PersonContext:
    """What the planner knows of the person: their standing instructions (Settings →
    Memory) and what they said of their latest runs (``run_feedback``)."""

    instructions: str
    lessons: tuple[Lesson, ...]


def person_context(user: CurrentUser, session: DbSession) -> PersonContext:
    return PersonContext(
        user_memory.instructions_for(session, user), run_feedback.lessons_for(session, user)
    )


Person = Annotated[PersonContext, Depends(person_context)]


@dataclass(frozen=True)
class PlannerContext:
    """What a planner request needs besides its body: the provider, the profile,
    the person's tools, their standing instructions and what they said of their runs."""

    providers: ProviderFactory
    profile: LLMProfile
    catalog: PipelineToolCatalog
    instructions: str
    lessons: tuple[Lesson, ...] = ()


def planner_context(
    providers: Providers, profile: Profile, catalog: ToolCatalog, person: Person
) -> PlannerContext:
    return PlannerContext(providers, profile, catalog, person.instructions, person.lessons)


Planner = Annotated[PlannerContext, Depends(planner_context)]


def run_executor(request: Request) -> RunExecutor:
    """Where runs execute: the app's background executor (tests swap it)."""
    executor: RunExecutor = request.app.state.run_executor
    return executor


Executor = Annotated[RunExecutor, Depends(run_executor)]


def run_service(request: Request, executor: Executor, settings: AppSettings) -> RunService:
    return RunService(
        request.app.state.database,
        executor,
        settings.pipeline_max_parallel_steps,
        run_policy(settings),
    )


Runs = Annotated[RunService, Depends(run_service)]


@dataclass(frozen=True)
class RunAnswering:
    """Who answers a run's request (an approval, a question), and what records it."""

    user: User
    runs: RunService


def run_answering(user: CurrentUser, runs: Runs) -> RunAnswering:
    return RunAnswering(user, runs)


RunAnswers = Annotated[RunAnswering, Depends(run_answering)]


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
    request: Request,
    user: CurrentUser,
    profile: Profile,
    context: PipelineRun,
    schedules: Schedules,
) -> AgentFactory:
    """Defer agent construction until after the chat request is validated. Its
    run_pipeline tool records runs like the Runs screen does, and its schedule
    tools use the signed-in user's own schedules."""
    database = request.app.state.database
    calls = calls_of(UsageKind.PLANNER, profile.default_model)
    metering = planner_metering(account_meter(database, user.id, profile, calls), profile)
    planner = partial(get_planner_provider, metering=metering)
    scope = ChatScope(database, user, profile, context.runs, context.agents, schedules, planner)
    return partial(get_chat_agent, scope)


Agents = Annotated[AgentFactory, Depends(agent_factory)]


def chat_access(user: CurrentUser, session: DbSession, settings: AppSettings) -> ChatAccess:
    return ChatAccess(session, user, settings.chats_max_per_user)


Chats = Annotated[ChatAccess, Depends(chat_access)]


def chat_memory(request: Request, user: CurrentUser, settings: AppSettings) -> ChatMemory:
    """What the chat remembers for the signed-in user. It opens its own short
    transactions: the request's session may be closed while a reply still streams."""
    limits = MemoryLimits(
        settings.chat_history_max_chars, settings.chat_summary_max_chars, settings.chat_max_messages
    )
    return ChatMemory(request.app.state.database, user, limits)


Memory = Annotated[ChatMemory, Depends(chat_memory)]


#: The request's "now", in UTC; a test fixes it by overriding ``utcnow``.
Now = Annotated[datetime, Depends(utcnow)]


def schedule_access(
    user: CurrentUser, session: DbSession, settings: AppSettings, now: Now
) -> ScheduleAccess:
    """The signed-in user's schedules (the builder's Schedule panel, Runs screen)."""
    limits = run_policy(settings).limits
    return ScheduleAccess(session, user, settings.schedules_max_per_user, now, limits)


Schedules = Annotated[ScheduleAccess, Depends(schedule_access)]

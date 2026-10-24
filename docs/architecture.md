# Architecture

## System view

```mermaid
graph LR
    Browser["React SPA<br/>Vite :4200"] -->|"/api/* + Bearer JWT<br/>(proxied in dev)"| API["FastAPI + Uvicorn<br/>:8000"]
    API -->|SQLAlchemy| DB[("SQLite")]
    API -->|"HTTPS, API key,<br/>LLM_TIMEOUT_SECONDS"| LLM["OpenRouter / TogetherAI"]
    API -->|"configured MCP tools<br/>MCP_TIMEOUT_SECONDS"| MCP["MCP servers<br/>(MCP_SERVERS)"]
    API -->|"streamable HTTP, https,<br/>public addresses only"| Own["Each user's MCP servers<br/>(Settings → Integrations)"]
```

The backend is a **chokepoint**: it holds the provider API key (the browser never
sees it), validates every model id against a catalogue, and bounds every
outbound call with a timeout. It also holds each user's integration header
values (encrypted, never sent back) and is the only thing that talks to those
servers.

## Backend layers

```mermaid
graph TD
    routes["api/routes.py<br/>routing only"] --> endpoints
    endpoints["api/endpoints/*<br/>HTTP boundary"] --> schemas["api/schemas/*<br/>contracts"]
    endpoints --> deps["api/deps.py<br/>session, user, provider"]
    endpoints --> services["api/services/*<br/>business logic"]
    endpoints --> repositories["api/repositories/*<br/>data access"]
    services --> repositories
    services --> models["api/models.py<br/>SQLAlchemy"]
    repositories --> models
    services --> llm["llm/*<br/>provider layer (no web or DB)"]
    services -. raise .-> exceptions["api/exceptions.py<br/>DomainError"]
    exceptions -. mapped by .-> errors["api/errors.py<br/>one error shape"]
```

Rules that keep this shape (full text in [AGENTS.md §2](../AGENTS.md)):

- **Endpoints are thin**: FastAPI validates the body against a pydantic schema,
  the endpoint calls a service or repository and returns a response schema. No
  business `if`s, no prompt building.
- **Protected by default**: every router except those in `PUBLIC_ROUTERS` is
  mounted behind the `current_user` dependency.
- **Services never touch HTTP**: they take and return plain Python values and
  dataclasses, and signal failure by raising a `DomainError`.
- **Only `api/errors.py` builds error responses**, always as
  `{"error": "<code>", "detail": "<message>"}`.
- **`llm/` never imports the web framework, the database or settings**: it
  receives a `ProviderConfig` dataclass.
  Only `api/services/llm.py` reads provider settings.
- **Ownership filtering lives in `api/repositories/`**, so "another user's
  pipeline" and "no such pipeline" look identical (404).

## Frontend layers

```mermaid
graph TD
    main["main.tsx<br/>Router + AuthProvider"] --> App["App.tsx<br/>routes + nav"]
    App --> features["features/&lt;feature&gt;/<br/>pages + use*.ts hooks"]
    features --> coreapi["core/api/<br/>client.ts gateway, endpoints, types"]
    features --> coreauth["core/auth/<br/>AuthContext, RequireAuth"]
    features --> corehooks["core/hooks/useModels"]
    features --> coreui["core/ui/<br/>shared presentation + React Bits motion"]
    coreapi --> tokens["core/auth/tokenStorage<br/>sole localStorage owner"]
    coreauth --> tokens
```

Components render and handle input. `fetch`, the bearer token, timeouts, and
error mapping live in `core/api/client.ts`; feature state lives in a
`use<Feature>.ts` hook next to the page.

## Request traces

### 1. Run a pipeline — `POST /api/pipelines/<id>/run`

```mermaid
sequenceDiagram
    participant UI as usePipelineBuilder
    participant C as core/api/client.ts
    participant E as endpoints/pipelines.run_pipeline
    participant R as repositories/pipelines
    participant S as services/pipelines.run
    participant P as services/multiagent/mapper
    participant G as services/multiagent/graph
    participant A as services/multiagent/step_agent
    participant U as services/agent_runtime
    participant T as services/mcp_discovery
    participant M as MCP servers + the user's integrations
    UI->>C: runPipeline(id, input) (timeout 1 h)
    C->>E: POST + Bearer token
    E->>E: FastAPI validates {"input"} / {"inputs"} against RunRequest
    E->>R: get_owned(user, id)
    R-->>E: Pipeline or raise NotFound (404)
    E->>S: ensure_runnable() then run(pipeline, agent generator, input, inputs)
    S->>P: snapshot_pipeline(pipeline)
    P-->>S: immutable PipelineSpec
    S->>S: bind_run_inputs (400 if the text/values do not match the declared inputs)
    S->>G: execute PipelineSpec as a StateGraph with RunInputs
    loop each stage in order
        G->>G: start step nodes on shared input (bounded concurrency)
        G->>A: execute agent for each step (async)
        A->>A: mcp_connections_for(user): MCP_SERVERS + enabled integrations
        A->>U: resolve selected tool policy
        U->>T: discover selected tools as needed
        T->>M: list tools (a failing integration is skipped)
        A->>M: call MCP tool if the agent selects it
        A-->>G: final text and tool name/status trace, or DomainError
        G->>G: join all step nodes; merge in saved order
    end
    G-->>S: RunResult dataclass
    S-->>E: RunResult dataclass
    E-->>C: 200 RunResponse
    C-->>UI: PipelineRunResponse
```

A pipeline may declare named inputs. `pipeline_inputs.bind_run_inputs` checks
the request against them before the graph starts: the first stage receives
their values (labelled when there are several), and the values travel in the
graph state so that `prompts.step_prompt` can fill `{name}` in a step of any
stage, next to `{input}`, the stage's input.

Each agent uses its selected model and optional role, and a system prompt from
`prompts.step_agent_system_prompt` that states the step's expected output when
it has one and, when the agent has tools, tells it to use them instead of
guessing, cite web sources and adapt when a tool fails.
`allowed_tools: null` grants the signed-in user's pipeline list and inspect
tools, the enabled built-in web, calculation, clock and local workspace tools
(see below), all configured MCP tools and the tools of the user's enabled
integrations; `[]` grants none;
an explicit list grants only named tools. A missing selected tool raises
`tool_unavailable`, naming it. The graph keeps step results in saved order even if agents
finish out of order. The response contains tool call names and success/error
statuses, without arguments or tool output. A built-in tool that fails (a page
that times out, a refused address, a bad expression) returns an error result
to the agent, which can retry another way; the call shows as `error` in the
trace and the run continues. Model, MCP, and timeout failures stop the whole
run; no partial result is returned.

### Built-in tools

`api/services/toolbox/` gives agents real work to do without any MCP server.
`registry.py` maps each tool name to a builder (Strategy + Registry);
`AGENT_BUILTIN_TOOLS` picks the entries on offer, and a builder returns nothing
when its tool is not configured, so `web_search` appears only when
`TAVILY_API_KEY` is set. `tools.py` adapts the helpers into LangChain tools with
`handle_tool_error`; `web.py` is the httpx gateway (Tavily search, page fetch);
`calculator.py` evaluates arithmetic over a whitelisted AST, never `eval`;
`html_text.py` reduces HTML to readable text; `workspace.py` confines file listing,
search, text/CSV reads and new artifacts to a per-user directory below
`AGENT_WORKSPACE_DIR`, without hidden
paths, symlink traversal or overwrites. `agent_tools.native_tools` joins
them with the pipeline tools, so pipeline agents, the chat agent, the planner
and `GET /agent-tools` all see the same set.

`fetch_url` only reaches public addresses: every redirect hop is resolved and
refused if any address is loopback, private, link-local or otherwise
non-global, which keeps a prompt-injected agent out of the server's network and
cloud metadata endpoint. httpx resolves the host again when it connects, so a
DNS-rebinding window remains; drop `fetch_url` from `AGENT_BUILTIN_TOOLS` where
that is unacceptable. Outbound web tools are automatically removed when
workspace readers are offered unless the operator explicitly sets
`AGENT_ALLOW_WORKSPACE_NETWORK_ACCESS=true`. Downloads stop at `WEB_FETCH_MAX_BYTES`, the text handed
to the model at `WEB_FETCH_MAX_CHARS`, and each request at
`WEB_TIMEOUT_SECONDS`, with no retries.

`run_python` lets an agent run code for data analysis and charts, offered only
when `E2B_API_KEY` is set. Code never runs in the web process: `sandbox.py`
defines the `CodeSandbox` port (Adapter) and one call's lifecycle, and
`e2b_sandbox.py`, the only importer of the e2b-code-interpreter SDK, creates a
fresh E2B cloud sandbox per call with no internet access, authenticated URLs,
a lifetime of `SANDBOX_TIMEOUT_SECONDS` and kill-on-timeout. One deadline of
that same timeout covers the whole call (creating the sandbox, uploading the
inputs, running the code, collecting its files); it starts before the sandbox
exists, so the call, not the sandbox's death, decides when it timed out. The
sandbox is closed in a shielded `finally`, so an error, a timeout or a
cancelled agent still destroys it. `code_runner.py` reads the `input_files`
through `workspace.py` (same confinement and size limit, and a symlink to a
hidden file stays hidden) into `/home/user/inputs/`, saves what the code
writes to `/home/user/outputs/` and the PNG charts it displays into a new
`sandbox/<UTC time>/` workspace folder (`outputs/` and `charts/` inside it; at
most `SANDBOX_MAX_FILES` files within `WORKSPACE_MAX_FILE_BYTES`, never
overwriting), and returns the error with a short traceback, the saved files,
the files not saved and why, the final result, stdout and stderr, cut at
`SANDBOX_MAX_OUTPUT_CHARS`. Outputs are downloaded as streams and dropped once
they outgrow the file limit; one that cannot be fetched is reported without
failing the call. A run that streams back more than
`SANDBOX_MAX_STREAM_CHARS` is stopped, because the SDK holds all of it in
memory; the SDK reads each message whole, so one single huge message is not
bounded by it. An exception in the code, a timeout and an E2B failure are
error results the agent can react to. The SDK is async, so
sandbox calls do not block the event loop; workspace disk work runs in a
worker thread. `sandbox.run` is logged with its outcome and duration, never
the code or its output.

`run_python` counts as a workspace reader, since its `input_files` read the
workspace, so when it is offered it also removes the outbound web tools unless
`AGENT_ALLOW_WORKSPACE_NETWORK_ACCESS=true` (without an E2B key it is not
offered and removes nothing). It is not outbound itself: E2B
creates the sandbox with `allow_internet_access=False`, which denies all of its
outbound traffic, so the code can only hand data back to the agent. The code
(which can embed anything in the agent's context) and the input files the
agent names do leave the server for E2B, the operator's chosen provider, the
way prompts go to the LLM provider.

### MCP servers and tool discovery

Agents get MCP tools from two places: the operator's `MCP_SERVERS` (shared,
trusted configuration, HTTP or stdio) and each user's own **integrations**
(Settings → Integrations, `api/services/integrations/`). One function,
`integrations.connections.mcp_connections_for(database, user, settings)`, builds
both into an `MCPConnections(operator, user)` value; the chat agent
(`agent.py`), pipeline step agents (`multiagent/step_agent.py`) and the
catalogue (`tool_catalog.py`, behind `GET /agent-tools` and the planner) all
call it, so they always agree on what a user can reach.

`mcp_discovery.discover_tools` loads the tools, every name prefixed with its
server's name:

- **Operator servers** load together, as before: if one fails, discovery fails
  with `tool_unavailable`, and duplicate names among native and operator tools
  are refused.
- **Integrations** load one by one through `load_server_tools`, the adapter
  that turns any MCP SDK failure into a `ToolUnavailable` with a plain reason.
  One that fails is skipped with a logged warning
  (`integration.discovery_skipped`), so runs and chats that do not need it keep
  working; a step that *selected* one of its tools then fails in
  `agent_runtime.resolve_tools`, because the tool is missing. A tool whose name
  is taken or is not a valid model-API function name is dropped, and the rest
  are tagged with their integration so the catalogue shows its name as the
  source.

The builder skips (and logs) an integration whose name an operator server now
uses, whose URL the current settings refuse, or whose header values
`SECRET_KEY` can no longer decrypt.

Users' servers are untrusted input to the server's network, so they are held
to the `fetch_url` rules, which live in `api/services/addresses.py` for both:
streamable HTTP only (never stdio, which would run a command on this server),
`https` (plain `http` only when `APP_ENV=local`), and a host that resolves only
to public addresses. The check runs when an integration is saved, before a
connection test, and before **every** request to it: the integration's
connection carries a `GuardedClientFactory` whose httpx request hook resolves
the host again (each discovery and tool call opens its own session). The MCP
SDK follows redirects only within the same origin, and that request is
checked too. httpx still resolves the name once more when it connects, so a
DNS server that answers differently within those milliseconds (DNS rebinding)
remains possible; this is the same window `fetch_url` accepts. Local
development reaches a server on `127.0.0.1` with `APP_ENV=local` and
`INTEGRATIONS_ALLOW_PRIVATE_NETWORK=true`, which also drops the per-request
guard; production refuses to start with that setting.

The graph lives in `api/services/multiagent/`: `contracts.py` defines immutable
pipeline and step snapshots, results, and the async step-agent contract;
`mapper.py` copies loaded ORM records into a `PipelineSpec`; `graph.py` composes
one node per saved step and a barrier after each stage; `step_agent.py` binds
the selected model, role, and tools. `pipelines.py` remains the facade for saved
run validation and planning. Chat and pipeline agents share tool policy and
error mapping in `agent_runtime.py`. This is a modular package inside the
FastAPI backend, with no change to the REST request or response.

The HTTP request still waits for the graph to finish. There is no durable run
record, LangGraph checkpoint for the pipeline, or approval flow for tool actions.

### 2. Stream chat — `POST /api/chat`

1. `useChatStream.send` adds the user message and an empty AI message, then
   iterates `streamChatReply()` → `client.streamText()`, which reads
   `response.body.getReader()` and yields decoded chunks.
2. `endpoints/chat.chat` validates `{"prompt"}` and calls
   `services/chat.stream_reply(agent, prompt)`.
3. `services/agent` builds a chat-only LangGraph agent from the configured
   model, binds the signed-in user's native pipeline tools, and discovers tools
   from every server in `MCP_SERVERS` and the user's enabled integrations. Graph execution runs in one producer
   task, which sends assistant text through a queue. Model and MCP calls have
   timeouts; tool results stay out of the text stream. Shared tool policy and
   error mapping live in `services/agent_runtime`.
4. `stream_reply` **pulls the first chunk eagerly**. If agent setup or a tool
   fails before text appears, a `DomainError` is raised while the response is
   still uncommitted, so the client gets a real 5xx error body.
5. After the first chunk the response is a `StreamingResponse`
   (`text/plain`); Starlette iterates the async generator. A failure
   mid-stream can no longer change the status, so it is logged
   (`chat.stream_interrupted`) and the stream simply ends.
6. The hook appends each chunk to the AI message; unmounting aborts the fetch.

### 3. Generate a pipeline — `POST /api/pipelines/generate`

1. `GenerateRequest` validates `description` and an optional
   `planner_model` (defaults to the configured default model).
2. `services/tool_catalog` discovers the native pipeline tools, the
   configured MCP tools and the user's integration tools.
   `services/pipelines.generate` builds a prompt with
   their names and descriptions plus the allowed model ids, then calls the
   direct provider adapter.
3. `parse_plan` extracts the first `{...}` block, parses JSON, requires `name`
   and a non-empty `steps` list, fills a missing `order`, replaces unknown model
   ids with the default, removes unavailable names from explicit tool
   allowlists, clips each step's `expected_output`, and keeps only the planned
   `inputs` whose names follow the same rule the save endpoint enforces.
   Unusable output → `upstream_response_invalid` (502).
4. The endpoint returns the plan **without saving it**. The user edits it in
   `AutoPipelinePage` and saves through the normal `POST /api/pipelines/`.

`GET /api/agent-tools` uses the same catalogue and returns each tool's exact
name, description, and source for the builder: `AIMIx`, `MCP`, or the name of
the user's integration it comes from.

### 4. Revise a pipeline — `POST /api/pipelines/revise`

```mermaid
sequenceDiagram
    participant UI as RevisePanel + useRevisePipeline
    participant C as core/api/client.ts
    participant E as endpoints/pipelines.revise_pipeline
    participant T as services/tool_catalog
    participant S as services/pipeline_revision.revise
    participant B as services/prompts
    participant P as services/pipelines.ask_planner
    participant D as services/pipeline_changes
    UI->>C: revisePipeline(draft, instruction) (timeout 1 h, aborted on unmount or Stop)
    C->>E: POST + Bearer token
    E->>E: ReviseRequest validates the draft and the instruction
    E->>T: available_sync()
    E->>S: revise(provider, profile, RevisionRequest, tools)
    S->>B: pipeline_revision_prompt(draft, instruction, models, tools)
    S->>P: ask_planner(provider, profile, PlannerCall)
    P-->>S: plan sanitised by parse_plan, as for generate
    S->>D: diff_pipelines(draft, plan)
    D-->>S: list of PipelineChange
    S-->>E: Revision(pipeline, changes)
    E-->>C: 200 ReviseResponse
    C-->>UI: change list + preview, then Apply or Discard
```

1. The draft is the builder's or the auto page's current pipeline, saved or not.
   `PipelineDraftIn` checks it like a save, except that its name and step
   prompts may be blank, and `instruction` is non-blank and bounded.
2. `prompts.pipeline_revision_prompt` is built from the same
   `PIPELINE_PLANNER_GUIDE` as the generation prompt (tools, inputs, step
   fields, stages, reply format) plus the revision rules: change only what was
   asked, copy every other step exactly, keep `{input}` and `{name}` valid, add
   or remove inputs only when needed. The draft (as JSON) and the instruction
   are user data, so each sits in its own tagged block; the tags are stripped
   from the content, so it cannot close its block and pass for instructions.
3. `pipelines.ask_planner` is the one call-and-parse path, shared with
   `generate`: provider failures map through `PROVIDER_ERROR_MAP`, and the
   answer goes through `parse_plan` (unusable output → 502).
4. `pipeline_changes.diff_pipelines` is a pure function: it pairs steps (same
   content, then title, then prompt, then position), compares fields and
   inputs, and reports a stage change only when a step really runs at another
   point. The endpoint returns the revision, the changes and the models.
5. **Nothing is saved.** Apply in the UI replaces the draft and marks it
   unsaved; the user saves through `POST`/`PUT /api/pipelines/`. A proposal
   belongs to the draft it was made from, so editing the draft sets it aside.

## Error flow

```
llm/ retries a transient failure (llm/retry.py), then raises LLMError subclass
  → services translate via api/services/errors.PROVIDER_ERROR_MAP
  → DomainError (code + status) propagates out of the endpoint
  → FastAPI calls the handler installed by api/errors.install_error_handlers
  → {"error": code, "detail": message} with the mapped status
  → core/api/client.ts turns it into ApiError(message, status, code)
```

Request validation errors become 400 `validation_error`. Framework HTTP errors
(unknown route 404, 405, …) are mapped by `STATUS_CODES` in `api/errors.py`. An
unexpected exception becomes a 500 `server_error` and is still logged by the
server — never a 200 with an error inside.

## Design patterns in use

| Pattern | Where | Why |
|---|---|---|
| Registry + Factory | `llm/registry.py`, `api/services/llm.get_provider` | New provider = one dict entry, no `if` chain |
| Adapter | `llm/base.OpenAICompatibleProvider`, `api/services/multiagent/mapper.py`, `step_agent.py` | Wrap provider SDKs, snapshot ORM records, and bind agents to a graph port |
| Strategy map | `api/services/errors.PROVIDER_ERROR_MAP`, `api/services/mcp_discovery.REASONS` | Provider error → domain error, MCP failure → plain reason, each in one place |
| Decorator (retry) | `llm/retry.Retrier`, `llm/agent_models.RetryingChatModel` | One bounded retry policy around every model call, direct or LangChain |
| Repository | `api/repositories/pipelines.py`, `users.py` | Ownership-scoped queries and atomic writes |
| Graph orchestration | `api/services/multiagent/graph.py` | Concurrent agent nodes and a stage join with deterministic output order |
| Dependency Injection | `api/deps.py` | Session, settings, user and provider swappable in tests |
| Application Factory | `api/main.create_app` | One place wires settings, database, middleware and routes |
| Builder | `api/services/prompts.py` | Prompt text kept apart from transport |
| DTO / Value Object | `StepResult`, `RunResult`, `ProviderConfig`, `ModelInfo` | Frozen dataclasses across layers |
| Gateway | `frontend/src/core/api/client.ts` | Token, timeout, error mapping in one place |
| Provider/Context | `frontend/src/core/auth/AuthContext.tsx` | Shared auth state |

# AIMIx documentation

In-depth documentation for developers who run, change, or maintain AIMIx.
The top-level [README](../README.md) is the short pitch and quick start;
[AGENTS.md](../AGENTS.md) holds the binding engineering rules. This folder
explains **how the code actually works** and **how to change it safely**.

For a visual introduction, open [the HTML codebase guide](codebase-guide.html) in
your browser. It includes use-case stories, a step-by-step execution walkthrough,
class and function relationships, and links to the implementation. It works offline.

## Reading order

If you are new to the repository, read these in order:

| # | Document | You will learn |
|---|---|---|
| 1 | [getting-started.md](getting-started.md) | Install, configure, run, and troubleshoot the app locally |
| 2 | [architecture.md](architecture.md) | The layers, the dependency rules, and three end-to-end request traces |
| 3 | [backend.md](backend.md) | Every backend module: what it owns and what it must not do |
| 4 | [llm-providers.md](llm-providers.md) | The provider layer, the model catalogue, adding a provider or model |
| 5 | [frontend.md](frontend.md) | The React app: routing, `core/`, features, auth, streaming |
| 6 | [api-reference.md](api-reference.md) | Every HTTP endpoint with request and response examples |
| 7 | [development-guide.md](development-guide.md) | Daily workflow, recipes for common changes, testing, quality gates |
| 8 | [known-issues.md](known-issues.md) | Current gaps and technical debt, with suggested fixes |

## What AIMIx is, in one paragraph

A user signs in and builds a **pipeline** of agent steps, each with a role,
prompt, model, and tool policy. Stages run in order; steps in one stage run in
parallel, and their text outputs feed the next stage through `{input}`. AIMIx
can also **generate** a pipeline from a description using the discovered tool
catalogue. A streaming **chat** agent can call native pipeline functions and
configured MCP tools. The FastAPI backend owns auth, persistence, and calls to
OpenRouter or TogetherAI; the React frontend provides the builder.

## Keeping these docs current

- A change that alters behaviour described here updates the matching page **in
  the same change** (a contract change already requires a frontend update, see
  AGENTS.md §6 — docs follow the same rule).
- Do not copy rules from `AGENTS.md` into these pages; link to the section.
- When you fix an item in [known-issues.md](known-issues.md), delete it there.

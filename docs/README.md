# AIMIx documentation

In-depth documentation for developers who run, change, or maintain AIMIx.
The top-level [README](../README.md) is the short pitch and quick start;
[AGENTS.md](../AGENTS.md) holds the binding engineering rules. This folder
explains **how the code actually works** and **how to change it safely**.

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

A user signs in and builds a **pipeline**: an ordered list of steps, each with
a prompt template and a model id. Running the pipeline sends the user's input to
step 1; each step's output becomes the next step's input (substituted into
`{input}`). AIMIx can also **generate** a pipeline from a plain-language
description by asking a "planner" model for JSON, and offers a streaming
**chat** screen. A Django backend owns auth, persistence, and every call to the
LLM provider (OpenRouter or TogetherAI); a React frontend is the UI.

## Keeping these docs current

- A change that alters behaviour described here updates the matching page **in
  the same change** (a contract change already requires a frontend update, see
  AGENTS.md §6 — docs follow the same rule).
- Do not copy rules from `AGENTS.md` into these pages; link to the section.
- When you fix an item in [known-issues.md](known-issues.md), delete it there.

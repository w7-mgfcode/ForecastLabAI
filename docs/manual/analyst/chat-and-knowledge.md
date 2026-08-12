# Chat and knowledge

The two chat agents, the RAG knowledge base they draw on, and the approval gate that keeps them honest.

**Purpose:** use the conversational layer productively, and understand exactly what it is allowed to do.
**Intended reader:** analysts using `/chat` and `/knowledge`.

## What you'll accomplish

Grounded answers with citations, an understanding of when an agent pauses and why, and a clear picture of the boundary around agent actions.

## Prerequisite

The agents need an LLM API key — `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` — in `.env`, or a local `ollama:` model configured. **Everything else in ForecastLabAI works without one:** forecasting, backtesting, the registry, the Explorer, and every analytical page.

## The RAG knowledge base

RAG — retrieval-augmented generation — answers from a body of indexed documents rather than the language model's general training alone. Here it grounds answers in **project documentation**.

### How indexing works

1. A document is split into overlapping **chunks** — markdown by heading, OpenAPI specs by endpoint.
2. Each chunk becomes an **embedding**: a numeric vector capturing its meaning.
3. Chunks and embeddings are stored in PostgreSQL via **pgvector**.

Indexing is **idempotent**. A document is identified by its path and a content hash, so re-indexing unchanged content does nothing, and changed content replaces the old chunks cleanly. You can safely re-index everything on a schedule.

Chunking is tunable: `rag_chunk_size` (512 tokens), `rag_chunk_overlap` (50), `rag_min_chunk_size` (100).

### How retrieval works

A query is embedded the same way and compared against every stored chunk by **cosine similarity**. Chunks above `rag_similarity_threshold` (default 0.7) are returned — up to `rag_top_k` (default 5) — each with a relevance score and a citation.

**Retrieval returns evidence, not an answer.** It hands back passages; the agent decides what to do with them. That separation is why answers can carry citations you can check.

If retrieval returns nothing for an obviously relevant question, the threshold is the usual cause — it is a floor, and different embedding models score differently against it.

### Embedding providers

Embeddings come from **OpenAI** or a local **Ollama** server. Ollama keeps document content off external services entirely.

The active provider, model, and vector dimension are visible and changeable under **Admin → AI models** (`GET` / `PATCH /config/ai`), live with no restart.

**`rag_embedding_dimension` must match the model's output width** — 1536 for OpenAI `text-embedding-3-small`, 768 for `nomic-embed-text`. The vector column has a fixed width, so a mismatch is a schema error, not a quality problem: changing dimension requires a migration and re-indexing the corpus.

### Using it

- **Knowledge page** (`/knowledge`) — browse the corpus, run live semantic searches, and see the system state the agents draw on: seeded data, model runs, deployment aliases.
- **Admin → RAG Sources** — index, list, and delete documents.
- **API** — `POST /rag/index`, `POST /rag/retrieve`, `GET /rag/sources`, `DELETE /rag/sources/{source_id}`.

An empty corpus means the assistant has nothing to cite. Index relevant documentation first — this manual is a reasonable place to start.

## The two agents

Built with PydanticAI:

- **`rag_assistant`** — answers questions from the knowledge base.
- **`experiment`** — can run forecasting experiments: training, backtesting, registry actions, and proposing scenarios.

### Talking to one

Use the **Chat** page (`/chat`) or the API:

| Endpoint | Purpose |
|---|---|
| `POST /agents/sessions` | Open a session, choosing the agent type. |
| `GET /agents/sessions/{id}` | Session status and message history. |
| `POST /agents/sessions/{id}/chat` | Send a message, get the full response. |
| `POST /agents/sessions/{id}/approve` | Approve or reject a pending tool call. |
| `DELETE /agents/sessions/{id}` | Close the session. |
| `WS /agents/stream` | Token-by-token streaming with tool-call events. |

A session keeps its history, so the agent remembers earlier turns.

### Tools, and why they are visible

Agents call **tools** — typed functions that fetch data or perform actions. The chat UI shows every call and its result.

That visibility is the point. An answer you can trace through "it called `list_runs`, got these rows, then said this" is checkable in a way a bare paragraph is not. Watching the tool trace is the fastest way to understand how an answer was reached — and to notice when an agent is confidently wrong about something it never looked up.

## The human-in-the-loop approval gate

Most tools are read-only and run immediately. Tools that **change state** do not.

When an agent wants to run a gated tool:

1. The session enters `awaiting_approval` and emits an `approval_required` event.
2. **Nothing happens.** The agent waits.
3. You approve or reject — in the chat, or via `POST /agents/sessions/{id}/approve`.
4. On approval the tool runs; on rejection it is skipped and the agent continues without it.

A pending approval expires after `agent_approval_timeout_minutes` (default 60), and the tool does not run.

The gated set is `agent_require_approval`, which ships as:

```
["create_alias", "archive_run", "save_scenario"]
```

Those are precisely the mutating tools: pointing an alias at a run, archiving a run, and persisting a scenario plan. **An agent can never silently mutate the registry** — a person is always in the loop for consequential actions.

This is a configured list, not a hard-coded law, which is the honest framing: removing a name from it *would* let the agent act unattended. That is why widening an agent's mutation surface without adding the tool to this list is forbidden by [AGENTS.md](../../../AGENTS.md), and why `save_scenario` was added to the list when the agent gained the ability to save scenarios.

If the agent seems to stop mid-task, check for a pending approval before assuming it hung.

## Session limits

Bounded so an agent cannot run away:

| Limit | Setting | Default |
|---|---|---|
| Tool calls per session | `agent_max_tool_calls` | 10 |
| Wall-clock per run | `agent_timeout_seconds` | 120 |
| Response tokens | `agent_max_tokens` | 4096 |
| Session lifetime | `agent_session_ttl_minutes` | 120 |
| Concurrent sessions per user | `agent_max_sessions_per_user` | 5 |

The **Agent Guide** page (`/guide`) shows these live, with the available tools and example prompts. Because it reads the running configuration, it cannot drift from reality the way a document can.

An agent that gives up partway through a long task has usually hit the tool-call cap or the timeout.

## Models and fallback

`agent_default_model` is the primary; `agent_fallback_model` is used when it fails. Both are `provider:model-name` over `anthropic`, `openai`, `google-gla`, `google-vertex`, or `ollama`.

If **both** fail, the API returns an `agent-fallback-exhausted` problem response — a distinct error type, so "the LLM provider is down" is diagnosable rather than surfacing as a generic 500.

Choosing an `ollama:` model runs the agent fully locally with no API key. Swap models live at **Admin → AI models**; identifier validation and its three rejection cases are in the [configuration reference](../configuration.md#the-model-identifier-format).

## A typical exchange

You ask a question on `/chat` → the `rag_assistant` calls its retrieval tool → the tool runs a semantic search over the corpus → the agent reads the returned passages → it answers, grounded in real documentation, with citations you can open.

For experiments, the `experiment` agent can additionally trigger training or backtesting, and propose a scenario — pausing for your approval before anything that writes.

## Using it well

- **Index first.** An empty corpus produces confident, ungrounded answers.
- **Read the tool trace,** especially when an answer surprises you.
- **Treat an approval prompt as a decision,** not a dialog to dismiss. It is the same gate that protects the registry.
- **Prefer the deterministic surfaces for decisions.** The Champion selector's ranking and the safety-stock heuristic involve **no LLM at all**. The agent is a way to explore and explain; it is not the thing that decides which model wins.

## Next

- [API reference](../integrator/api-reference.md) — calling any of this from code.
- [Configuration reference](../configuration.md) — every agent and RAG setting.

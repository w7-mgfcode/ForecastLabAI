# Agents and RAG Guide

ForecastLab includes a conversational AI layer — chat agents — backed by a
**RAG knowledge base** (retrieval-augmented generation). This guide explains how both
work and how to use them safely.

## The RAG Knowledge Base

RAG lets the system answer questions using a body of indexed documents rather than
only the language model's general training. ForecastLab uses it to ground answers in
**project documentation**.

### How indexing works

When you index a document:

1. The document is split into overlapping **chunks** (markdown is split by heading,
   OpenAPI specs by endpoint).
2. Each chunk is converted into an **embedding** — a numeric vector capturing its meaning.
3. Chunks and embeddings are stored in PostgreSQL using the `pgvector` extension.

Indexing is **idempotent**: each document is identified by its path and a content
hash, so re-indexing unchanged content does nothing, and changed content replaces the
old chunks cleanly.

### How retrieval works

A search query is embedded the same way, then compared against every stored chunk by
**cosine similarity**. The closest chunks above a similarity threshold are returned,
each with a relevance score and a citation back to its source document. Retrieval
returns evidence — passages — not a generated answer; the agent decides what to do
with them.

### Using it

- **Knowledge page** (`/knowledge`) — browse the indexed corpus and run live semantic
  searches.
- **Admin → RAG Sources** — index a new document, list sources, or delete one.
- **API** — `POST /rag/index`, `POST /rag/retrieve`, `GET /rag/sources`,
  `DELETE /rag/sources/{id}`.

### Embedding providers

Embeddings come from either **OpenAI** or a local **Ollama** server. The active
provider, model, and vector dimension are shown and changed under **Admin → AI models**
(`GET` / `PATCH /config/ai`). Local Ollama keeps document content off external services.

## The Chat Agents

The agents are conversational assistants built with PydanticAI. Two agent types exist:

- **`rag_assistant`** — answers questions using the RAG knowledge base.
- **`experiment`** — can run forecasting experiments (training, backtesting, registry
  actions) on your behalf.

### Talking to an agent

Use the **Chat** page (`/chat`) or the API:

1. `POST /agents/sessions` — open a session, choosing the agent type.
2. `POST /agents/sessions/{id}/chat` — send a message and get the full response, or
   connect to `WS /agents/stream` for token-by-token streaming.
3. `DELETE /agents/sessions/{id}` — close the session.

A session keeps its message history, so the agent remembers earlier turns in the
conversation.

### Tools

Agents can call **tools** — typed functions that fetch data or perform actions
(retrieve documentation, list model runs, start a backtest, and so on). When an agent
uses a tool, the chat UI shows the call and its result, so you can see exactly how an
answer was produced.

## The Human-in-the-Loop Approval Gate

Most tools are read-only and run immediately. Tools that **change state** — for
example creating a registry alias or archiving a run — are different: they **pause and
wait for your approval**.

When an agent wants to run one of these tools:

1. The session enters an `awaiting_approval` state and an `approval_required` event is
   emitted.
2. Nothing happens until you respond.
3. You approve or reject via `POST /agents/sessions/{id}/approve` (the Chat page
   surfaces this as a prompt).
4. On approval the tool runs; on rejection it is skipped.

This gate means an agent can never silently mutate the model registry — a person is
always in the loop for consequential actions. The set of approval-gated tools is a
deliberate, fixed list.

### Other safety limits

Each session is bounded so an agent cannot run away:

- a **token budget** per session,
- a **maximum number of tool calls** per session,
- a **timeout** wrapping each agent run.

The **Agent Guide** page (`/guide`) shows these limits live, along with the available
tools and example prompts.

## Putting It Together

A typical RAG-assisted exchange: you ask a question on the Chat page → the
`rag_assistant` agent calls its retrieval tool → the tool runs a semantic search over
the indexed corpus → the agent reads the returned passages → it answers, grounded in
real documentation, and you can see the citations. For experiments, the `experiment`
agent can additionally trigger training or backtesting — pausing for your approval
before anything that writes to the registry.

## Tips

- The agents need an LLM API key (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY`) in `.env`.
  Without one, the chat features are unavailable but the rest of the system still works.
- For useful RAG answers, index relevant documentation first — an empty corpus means
  the assistant has nothing to cite.
- Watch the tool-call display in the chat: it is the simplest way to understand how
  the agent reached its answer.

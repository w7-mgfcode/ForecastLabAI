# PRP-10: Agentic Layer ("The Brain")

**Feature**: INITIAL-10.md — Agentic Layer
**Status**: Ready for Implementation
**Confidence Score**: 8.0/10
**Last Updated**: 2026-02-01 (Post Phase-9 RAG Review)

---

## Goal

Build the Agentic Layer using PydanticAI providing:
1. **Experiment Orchestrator Agent** - Autonomous model experimentation workflow
2. **RAG Assistant Agent** - Evidence-grounded Q&A with citations
3. **Human-in-the-Loop Approval** - Blocking sensitive actions until approved
4. **WebSocket Streaming** - Real-time token delivery to clients
5. **Session Management** - Persistent state across multi-turn conversations

This is the "Brain" layer that orchestrates tools from INITIAL-9 (RAG), Phase 5 (Backtesting), and Phase 6 (Registry).

---

## Why

- **Autonomous Experimentation**: Agent runs backtests, compares results, deploys winners
- **Evidence-Grounded Answers**: RAG-powered Q&A prevents hallucination
- **Safety Controls**: Human approval for deployment actions
- **Real-Time UX**: Streaming responses for responsive chat interface
- **Portfolio Value**: Demonstrates modern AI agent architecture

---

## What

### Endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| `POST` | `/agents/experiment/run` | Execute experiment workflow |
| `POST` | `/agents/experiment/approve` | Approve pending action |
| `POST` | `/agents/rag/query` | Query with answer generation |
| `GET` | `/agents/status/{session_id}` | Check session status |
| `WS` | `/agents/stream` | WebSocket for streaming |

### Success Criteria

- [ ] Agents produce schema-enforced structured outputs
- [ ] Tool calls logged with correlation IDs and timing
- [ ] Human-in-the-loop blocks sensitive actions
- [ ] WebSocket streaming delivers tokens in real-time
- [ ] Session state persists across requests
- [ ] Graceful LLM API failure handling with retries
- [ ] 60+ unit tests with mocked LLM responses
- [ ] 15+ integration tests (rate-limited real LLM calls)
- [ ] All validation gates green

---

## All Needed Context

### Documentation & References

```yaml
# CRITICAL - PydanticAI Documentation
- url: https://ai.pydantic.dev/
  why: "Official PydanticAI docs - main reference"

- url: https://ai.pydantic.dev/agents/
  why: "Agent constructor, output_type, system_prompt, run/run_stream methods"

- url: https://ai.pydantic.dev/tools/
  why: "@agent.tool decorator, RunContext, deps_type, tool parameters"

- url: https://ai.pydantic.dev/output/
  why: "AgentRunResult, StreamedRunResult, token usage tracking"

- url: https://ai.pydantic.dev/examples/chat-app/
  why: "FastAPI + streaming integration example"

- url: https://github.com/pydantic/pydantic-ai
  why: "Source code for edge cases"

# Anthropic API (fallback reference)
- url: https://docs.anthropic.com/en/api
  why: "Claude model IDs, rate limits, error codes"

# Codebase Patterns (CRITICAL)
- file: app/features/registry/service.py
  why: "Service pattern - __init__, get_settings(), structured logging"

- file: app/features/jobs/service.py
  why: "Job execution pattern - state machine, error handling, audit trail"

- file: app/features/backtesting/service.py
  why: "BacktestingService - the agent will call this via tools"

- file: app/features/registry/routes.py
  why: "Route patterns - APIRouter, response_model, HTTPException"

- file: app/features/registry/tests/conftest.py
  why: "Test fixtures - db_session, client, async patterns"

# RAG Integration (INITIAL-9 dependency)
- file: PRPs/PRP-9-rag-knowledge-base.md
  why: "RAG layer the agent will consume via retrieve_context tool"
```

### Current Codebase Tree (Relevant Parts)

```text
app/
├── core/
│   ├── config.py          # Settings - ADD agent settings
│   ├── database.py         # get_db dependency
│   ├── logging.py          # get_logger
│   └── exceptions.py       # ForecastLabError base
├── features/
│   ├── backtesting/        # Agent tool: run_backtest
│   ├── registry/           # Agent tools: list_runs, compare_runs, create_alias
│   ├── forecasting/        # Agent tool: list_models
│   ├── rag/                # INITIAL-9 - Agent tool: retrieve_context
│   └── agents/             # NEW: Create this vertical slice
├── main.py                  # Include agents router + WebSocket
```

### Desired Codebase Tree (Files to Create)

```text
app/features/agents/
├── __init__.py              # Export router
├── models.py                # AgentSession ORM model
├── schemas.py               # Request/Response Pydantic schemas
├── routes.py                # REST endpoints
├── websocket.py             # WebSocket endpoint handler
├── service.py               # AgentService orchestration
├── agents/
│   ├── __init__.py
│   ├── base.py              # Base agent configuration
│   ├── experiment.py        # Experiment Orchestrator Agent
│   └── rag_assistant.py     # RAG Assistant Agent
├── tools/
│   ├── __init__.py
│   ├── registry_tools.py    # list_runs, compare_runs, create_alias
│   ├── backtesting_tools.py # run_backtest
│   ├── forecasting_tools.py # list_models
│   └── rag_tools.py         # retrieve_context, format_citation
├── deps.py                  # AgentDeps dataclass for dependency injection
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Fixtures with mocked LLM
│   ├── test_schemas.py
│   ├── test_tools.py
│   ├── test_agents.py
│   ├── test_service.py
│   └── test_routes.py

alembic/versions/
└── xxxx_create_agent_sessions_table.py

examples/agents/
├── experiment_demo.py
├── rag_query.http
└── websocket_client.py
```

### Known Gotchas & Library Quirks

```python
# CRITICAL: PydanticAI model identifier format (updated Jan 2026)
# Use "anthropic:claude-sonnet-4-5" NOT "claude-sonnet-4-5"
# For production, pin specific version: "anthropic:claude-sonnet-4-5-20250929"
agent = Agent(model="anthropic:claude-sonnet-4-5")

# CRITICAL: deps_type must match RunContext generic parameter
agent = Agent(
    model="anthropic:claude-sonnet-4-5",
    deps_type=AgentDeps,  # Your dependency dataclass
)

@agent.tool
def my_tool(ctx: RunContext[AgentDeps], param: str) -> str:
    # ctx.deps is typed as AgentDeps
    db = ctx.deps.db
    ...

# CRITICAL: Use @agent.tool for context access, @agent.tool_plain without
@agent.tool_plain
def roll_dice() -> str:
    """No RunContext needed here."""
    return str(random.randint(1, 6))

# CRITICAL: output_type (not result_type) for structured outputs
agent = Agent(
    model="...",
    output_type=ExperimentReport,  # NOT result_type
)

# CRITICAL: run() is async, run_sync() is sync wrapper
result = await agent.run(prompt, deps=deps)  # Async
result = agent.run_sync(prompt, deps=deps)   # Sync

# CRITICAL: Streaming requires async context manager
async with agent.run_stream(prompt, deps=deps) as result:
    async for text in result.stream_text():
        yield text

# CRITICAL: Access token usage after run completes
print(result.usage())  # RunUsage(input_tokens=X, output_tokens=Y)

# CRITICAL: Message history for multi-turn
result2 = await agent.run(
    "follow-up question",
    deps=deps,
    message_history=result.messages,  # Previous messages
)

# CRITICAL: Tool docstrings become schema descriptions
@agent.tool
async def run_backtest(
    ctx: RunContext[AgentDeps],
    model_type: str,
    config: dict[str, Any],
) -> BacktestResult:
    """Run a backtest for a model configuration.

    Use this to evaluate model performance with time-series CV.
    Returns per-fold and aggregated metrics (MAE, sMAPE, WAPE).

    Args:
        model_type: Type of model (naive, seasonal_naive, moving_average)
        config: Model-specific configuration
    """
    ...

# CRITICAL: FastAPI WebSocket pattern
from fastapi import WebSocket, WebSocketDisconnect

@router.websocket("/agents/stream")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            # Process and stream response
            async for chunk in stream_agent_response(data):
                await websocket.send_json(chunk)
    except WebSocketDisconnect:
        pass

# CRITICAL: PydanticAI retry mechanism
from pydantic_ai import ModelRetry

@agent.tool
async def risky_tool(ctx: RunContext[AgentDeps]) -> str:
    try:
        return await external_api()
    except APIError as e:
        raise ModelRetry(f"API failed: {e}. Please try again.") from e
```

---

## Implementation Blueprint

### Data Models

#### ORM Model (models.py)

```python
"""Agent session persistence."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.shared.models import TimestampMixin


class SessionStatus(str, Enum):
    """Agent session states."""
    ACTIVE = "active"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    EXPIRED = "expired"
    FAILED = "failed"


class AgentType(str, Enum):
    """Available agent types."""
    EXPERIMENT_ORCHESTRATOR = "experiment_orchestrator"
    RAG_ASSISTANT = "rag_assistant"


class AgentSession(TimestampMixin, Base):
    """Persistent agent session for multi-turn conversations."""
    __tablename__ = "agent_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    agent_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(30), default=SessionStatus.ACTIVE.value)

    # Message history for multi-turn
    message_history: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    # Pending approval
    pending_action: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Usage tracking
    total_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timing
    last_activity: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

#### Dependencies (deps.py)

```python
"""Agent dependencies for tool access."""
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class AgentDeps:
    """Dependencies passed to agent tools via RunContext."""
    db: AsyncSession
    session_id: str
    request_id: str | None = None
```

#### Pydantic Schemas (schemas.py)

```python
"""Agent API schemas."""
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


# === Experiment Agent ===

class ExperimentConstraints(BaseModel):
    """Constraints for experiment search."""
    model_config = ConfigDict(extra="forbid")

    model_types: list[str] = Field(default_factory=lambda: ["naive", "seasonal_naive"])
    min_train_size: int = Field(default=60, ge=30)
    max_splits: int = Field(default=5, ge=1, le=20)


class ExperimentRequest(BaseModel):
    """Request to run experiment workflow."""
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(..., min_length=10, max_length=500)
    store_id: int = Field(..., ge=1)
    product_id: int = Field(..., ge=1)
    constraints: ExperimentConstraints = Field(default_factory=ExperimentConstraints)
    auto_deploy: bool = False
    session_id: str | None = None


class RunSummary(BaseModel):
    """Summary of a model run."""
    run_id: str
    model_type: str
    config: dict[str, Any]
    metrics: dict[str, float]


class BaselineComparison(BaseModel):
    """Comparison against baseline models."""
    vs_naive: dict[str, float] | None = None
    vs_seasonal_naive: dict[str, float] | None = None


class ExperimentReport(BaseModel):
    """Structured output from Experiment Agent."""
    objective: str
    methodology: str
    experiments_run: int
    best_run: RunSummary | None
    baseline_comparison: BaselineComparison | None
    recommendation: str
    approval_required: bool
    pending_action: str | None = None


class ToolCallSummary(BaseModel):
    """Summary of a tool call."""
    tool: str
    args: dict[str, Any]
    result_summary: str
    duration_ms: float


class ExperimentResponse(BaseModel):
    """Response from experiment workflow."""
    session_id: str
    status: Literal["completed", "awaiting_approval", "failed"]
    report: ExperimentReport | None = None
    tool_calls: list[ToolCallSummary] = Field(default_factory=list)
    tokens_used: int = 0
    duration_ms: float = 0


# === Approval ===

class ApprovalRequest(BaseModel):
    """Request to approve/reject pending action."""
    model_config = ConfigDict(extra="forbid")

    session_id: str
    action: str
    approved: bool
    comment: str | None = Field(None, max_length=500)


class ApprovalResponse(BaseModel):
    """Response from approval action."""
    session_id: str
    action: str
    status: Literal["executed", "rejected"]
    result: dict[str, Any] | None = None


# === RAG Agent ===

class RAGQueryRequest(BaseModel):
    """Request for RAG-powered Q&A."""
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=5, max_length=2000)
    session_id: str | None = None
    include_sources: bool = True


class Citation(BaseModel):
    """Citation from RAG retrieval."""
    source_type: str
    source_path: str
    chunk_id: str
    snippet: str
    relevance_score: float


class RAGQueryResponse(BaseModel):
    """Response from RAG query."""
    session_id: str
    answer: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    citations: list[Citation] = Field(default_factory=list)
    insufficient_context: bool = False
    tokens_used: int = 0
    duration_ms: float = 0


# === Session Status ===

class SessionStatusResponse(BaseModel):
    """Session status details."""
    session_id: str
    agent_type: str
    status: str
    created_at: datetime
    last_activity: datetime
    pending_action: dict[str, Any] | None = None
    tool_calls_count: int
    tokens_used: int


# === WebSocket Messages ===

class WSMessage(BaseModel):
    """WebSocket message from client."""
    type: Literal["query", "approve", "cancel"]
    agent: Literal["rag_assistant", "experiment_orchestrator"]
    payload: dict[str, Any]


class WSEvent(BaseModel):
    """WebSocket event to client."""
    type: Literal["token", "tool_call", "complete", "error"]
    content: str | None = None
    tool: str | None = None
    status: str | None = None
    summary: str | None = None
    session_id: str | None = None
    tokens_used: int | None = None
```

---

## Task List

### Task 1: Add Dependencies to pyproject.toml

```yaml
MODIFY: pyproject.toml
ADD to dependencies:
  - "pydantic-ai>=1.48.0"    # PydanticAI agent framework (v1 stable, API guaranteed)
  - "anthropic>=0.50.0"      # Anthropic SDK for Claude
  - "websockets>=13.0"       # WebSocket support (already in uvicorn[standard])

NOTE: PydanticAI v1.0 was released Sept 2025 with API stability guarantee.
      Current version is 1.48.0 (Jan 2026). Do NOT use 0.x versions.
```

### Task 2: Add Agent Settings to config.py

```yaml
MODIFY: app/core/config.py
ADD after RAG settings:

  # Agent LLM Configuration
  agent_default_model: str = "anthropic:claude-sonnet-4-5"
  agent_fallback_model: str = "openai:gpt-4o"
  agent_temperature: float = 0.1
  agent_max_tokens: int = 4096
  anthropic_api_key: str = ""  # Required

  # Agent Execution Configuration
  agent_max_tool_calls: int = 10
  agent_timeout_seconds: int = 120
  agent_retry_attempts: int = 3
  agent_retry_delay_seconds: float = 1.0

  # Human-in-the-Loop Configuration
  agent_require_approval: list[str] = ["create_alias", "archive_run"]
  agent_approval_timeout_minutes: int = 60

  # Session Configuration
  agent_session_ttl_minutes: int = 120
  agent_max_sessions_per_user: int = 5

  # Streaming Configuration
  agent_enable_streaming: bool = True
```

### Task 3: Create Alembic Migration

```yaml
CREATE: alembic/versions/xxxx_create_agent_sessions_table.py
PATTERN: Follow existing migration patterns

Key columns:
  - session_id (String 32, unique, indexed)
  - agent_type (String 50, indexed)
  - status (String 30)
  - message_history (JSONB)
  - pending_action (JSONB, nullable)
  - total_tokens_used (Integer)
  - tool_calls_count (Integer)
  - last_activity (DateTime TZ)
  - expires_at (DateTime TZ)
  - created_at, updated_at (TimestampMixin)
```

### Task 4: Create ORM Models

```yaml
CREATE: app/features/agents/models.py
MIRROR: app/features/registry/models.py pattern
INCLUDE:
  - SessionStatus enum
  - AgentType enum
  - AgentSession model with JSONB columns
```

### Task 5: Create Dependencies Dataclass

```yaml
CREATE: app/features/agents/deps.py
CONTENT:
  - AgentDeps dataclass
  - Fields: db (AsyncSession), session_id, request_id
```

### Task 6: Create Pydantic Schemas

```yaml
CREATE: app/features/agents/schemas.py
MIRROR: app/features/registry/schemas.py pattern
INCLUDE:
  - ExperimentRequest, ExperimentResponse, ExperimentReport
  - ApprovalRequest, ApprovalResponse
  - RAGQueryRequest, RAGQueryResponse, Citation
  - SessionStatusResponse
  - WSMessage, WSEvent
```

### Task 7: Create Tool Modules

```yaml
CREATE: app/features/agents/tools/registry_tools.py
TOOLS:
  - list_runs(ctx, filters) -> list[RunSummary]
      # Wraps: RegistryService.list_runs(db, page, page_size, model_type, status, store_id, product_id)
  - compare_runs(ctx, run_id_a, run_id_b) -> CompareResult
      # Wraps: RegistryService.compare_runs(db, run_id_a, run_id_b)
  - create_alias(ctx, alias_name, run_id) -> AliasResult
      # Wraps: RegistryService.create_alias(db, AliasCreate(...))
      # REQUIRES HUMAN APPROVAL
  - archive_run(ctx, run_id) -> ArchiveResult
      # Wraps: RegistryService.update_run(db, run_id, RunUpdate(status=RunStatus.ARCHIVED))
      # NOTE: No direct archive method - use update_run with ARCHIVED status
      # REQUIRES HUMAN APPROVAL

CREATE: app/features/agents/tools/backtesting_tools.py
TOOLS:
  - run_backtest(ctx, model_type, config, store_id, product_id, n_splits) -> BacktestResult
      # Wraps: BacktestingService.run_backtest(db, store_id, product_id, start_date, end_date, config)

CREATE: app/features/agents/tools/forecasting_tools.py
TOOLS:
  - list_models(ctx) -> list[ModelInfo]
      # Returns available model types: naive, seasonal_naive, moving_average, lightgbm (if enabled)

CREATE: app/features/agents/tools/rag_tools.py
TOOLS:
  - retrieve_context(ctx, query, top_k) -> list[ChunkResult]
      # Wraps: RAGService.retrieve(db, RetrieveRequest(query=query, top_k=top_k))
      # NOTE: RAG service uses retrieve() not retrieve_context()
  - format_citation(ctx, chunk) -> Citation
      # Transforms ChunkResult to Citation schema

CRITICAL for all tools:
  - Use @agent.tool decorator (not @agent.tool_plain) for db access
  - First param is RunContext[AgentDeps]
  - Detailed docstrings for LLM schema (Google/numpy style supported)
  - Structured logging with timing
  - Match actual service method signatures from Phase 5-9 implementations
```

### Task 8: Create Agent Definitions

```yaml
CREATE: app/features/agents/agents/base.py
CONTENT:
  - get_agent_settings() helper
  - Common model configuration

CREATE: app/features/agents/agents/experiment.py
CONTENT:
  - ExperimentReport output schema
  - experiment_agent = Agent(...)
  - System prompt for experiment orchestration
  - Tools: list_models, run_backtest, compare_runs, create_alias

CREATE: app/features/agents/agents/rag_assistant.py
CONTENT:
  - RAGResponse output schema
  - rag_agent = Agent(...)
  - System prompt for evidence-grounded answers
  - Tools: retrieve_context, format_citation
```

### Task 9: Create Agent Service

```yaml
CREATE: app/features/agents/service.py
MIRROR: app/features/jobs/service.py pattern

Class AgentService:
  async def run_experiment(self, db, request) -> ExperimentResponse:
    - Create/resume session
    - Build AgentDeps
    - Run experiment_agent with tools
    - Capture tool calls and timing
    - Handle approval_required check
    - Update session state
    - Return structured response

  async def run_rag_query(self, db, request) -> RAGQueryResponse:
    - Create/resume session
    - Run rag_agent with tools
    - Extract citations from tool results
    - Return structured response

  async def approve_action(self, db, request) -> ApprovalResponse:
    - Load session
    - Validate pending_action matches
    - Execute action if approved
    - Update session status
    - Return result

  async def get_session_status(self, db, session_id) -> SessionStatusResponse:
    - Load session
    - Return status details

  async def stream_response(self, db, message) -> AsyncGenerator[WSEvent]:
    - Route to appropriate agent
    - Use run_stream for token-by-token delivery
    - Yield WSEvent for each chunk
```

### Task 10: Create REST Routes

```yaml
CREATE: app/features/agents/routes.py
MIRROR: app/features/registry/routes.py pattern

Routes:
  POST /agents/experiment/run -> ExperimentResponse
  POST /agents/experiment/approve -> ApprovalResponse
  POST /agents/rag/query -> RAGQueryResponse
  GET /agents/status/{session_id} -> SessionStatusResponse

CRITICAL:
  - Structured logging with agents.* prefix
  - Handle LLM API errors gracefully
  - Timeout handling
```

### Task 11: Create WebSocket Handler

```yaml
CREATE: app/features/agents/websocket.py
PATTERN: FastAPI WebSocket with async iteration

Key functions:
  websocket_stream(websocket: WebSocket):
    - Accept connection
    - Receive JSON messages
    - Parse WSMessage
    - Call service.stream_response()
    - Send WSEvent for each chunk
    - Handle disconnect gracefully

CRITICAL:
  - Use asyncio.wait_for for timeout
  - Catch WebSocketDisconnect
  - Log all events with correlation ID
```

### Task 12: Register Router in main.py

```yaml
MODIFY: app/main.py
ADD import: from app.features.agents.routes import router as agents_router
ADD import: from app.features.agents.websocket import websocket_stream
ADD router: app.include_router(agents_router)
ADD websocket: app.add_api_websocket_route("/agents/stream", websocket_stream)
```

### Task 13: Create Test Fixtures

```yaml
CREATE: app/features/agents/tests/conftest.py
FIXTURES:
  - db_session: Async session with cleanup (follow registry/tests/conftest.py pattern)
  - client: AsyncClient with db override
  - mock_pydantic_ai_agent: Mock PydanticAI Agent (see pattern below)
  - sample_experiment_request: ExperimentRequest fixture
  - sample_rag_request: RAGQueryRequest fixture
  - sample_agent_session: AgentSession ORM fixture

MOCK PATTERN (following rag/tests/conftest.py mock_embedding_service):
```

```python
@pytest.fixture
def mock_pydantic_ai_agent():
    """Mock PydanticAI Agent for unit tests without LLM calls.

    Follows the mock_embedding_service pattern from RAG tests.
    Returns deterministic responses without API calls.
    """
    from unittest.mock import AsyncMock, MagicMock
    from app.features.agents.schemas import ExperimentReport, RunSummary

    # Create mock structured output
    mock_report = ExperimentReport(
        objective="Test objective",
        methodology="Tested naive and seasonal_naive models",
        experiments_run=2,
        best_run=RunSummary(
            run_id="test123",
            model_type="seasonal_naive",
            config={"season_length": 7},
            metrics={"mae": 5.0, "smape": 10.0},
        ),
        baseline_comparison=None,
        recommendation="Deploy seasonal_naive model",
        approval_required=False,
    )

    # Mock result object
    mock_result = MagicMock()
    mock_result.output = mock_report
    mock_result.usage.return_value = MagicMock(
        input_tokens=100,
        output_tokens=50,
    )
    mock_result.messages = []

    # Mock agent
    agent = MagicMock()
    agent.run = AsyncMock(return_value=mock_result)
    agent.run_stream = AsyncMock()

    return agent
```

### Task 14: Create Unit Tests

```yaml
CREATE: app/features/agents/tests/test_schemas.py
  - Test all request/response validation

CREATE: app/features/agents/tests/test_tools.py
  - Test each tool function with mocked deps
  - Test tool return types
  - Test error handling

CREATE: app/features/agents/tests/test_agents.py
  - Test agent with mocked LLM
  - Test structured output parsing
  - Test tool call ordering
```

### Task 15: Create Integration Tests

```yaml
CREATE: app/features/agents/tests/test_routes.py
@pytest.mark.integration:
  - test_experiment_run_creates_session
  - test_experiment_approval_workflow
  - test_rag_query_returns_citations
  - test_session_status_returns_details
  - test_websocket_streaming (with TestClient)
```

### Task 16: Create Examples

```yaml
CREATE: examples/agents/experiment_demo.py
  - Full experiment workflow demo

CREATE: examples/agents/rag_query.http
  - HTTP client examples

CREATE: examples/agents/websocket_client.py
  - Python WebSocket client example
```

### Task 17: Update .env.example

```yaml
MODIFY: .env.example
ADD:
  # Agent Configuration
  ANTHROPIC_API_KEY=sk-ant-...
  AGENT_DEFAULT_MODEL=anthropic:claude-sonnet-4-5
  AGENT_FALLBACK_MODEL=openai:gpt-4o
  AGENT_MAX_TOOL_CALLS=10
  AGENT_TIMEOUT_SECONDS=120
  AGENT_TEMPERATURE=0.1
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run FIRST
uv run ruff check app/features/agents/ --fix
uv run ruff format app/features/agents/

# Expected: No errors
```

### Level 2: Type Checking

```bash
# MUST be green
uv run mypy app/features/agents/
uv run pyright app/features/agents/

# Expected: 0 errors
```

### Level 3: Unit Tests

```bash
# No LLM calls required (mocked)
uv run pytest app/features/agents/tests/ -v -m "not integration"

# Expected: All pass
```

### Level 4: Integration Tests

```bash
# Requires PostgreSQL + API keys
docker-compose up -d
uv run alembic upgrade head
uv run pytest app/features/agents/tests/ -v -m integration

# Expected: All pass (rate-limited)
```

### Level 5: Manual Smoke Test

```bash
# Start API
uv run uvicorn app.main:app --reload --port 8123

# RAG Query
curl -X POST http://localhost:8123/agents/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "How does backtesting prevent data leakage?"}'

# Expected: {"session_id": "...", "answer": "...", "citations": [...]}

# Experiment (requires indexed RAG data)
curl -X POST http://localhost:8123/agents/experiment/run \
  -H "Content-Type: application/json" \
  -d '{
    "objective": "Find best model for store 1, product 1",
    "store_id": 1,
    "product_id": 1
  }'

# Expected: {"session_id": "...", "status": "completed", "report": {...}}

# WebSocket test
python examples/agents/websocket_client.py
```

---

## Final Validation Checklist

- [ ] All tests pass: `uv run pytest app/features/agents/tests/ -v`
- [ ] No linting errors: `uv run ruff check app/features/agents/`
- [ ] No type errors: `uv run mypy && pyright`
- [ ] Migration applies: `uv run alembic upgrade head`
- [ ] Manual smoke tests pass
- [ ] Structured logging with `agents.*` prefix
- [ ] Tool calls logged with timing
- [ ] Session state persists across requests
- [ ] Approval workflow blocks sensitive actions
- [ ] WebSocket streaming works

---

## Anti-Patterns to Avoid

- ❌ Don't use `result_type` - use `output_type` in PydanticAI
- ❌ Don't forget `deps_type` when using `RunContext[AgentDeps]`
- ❌ Don't use `@agent.tool_plain` when db access needed
- ❌ Don't forget to handle `WebSocketDisconnect`
- ❌ Don't block on LLM calls without timeout
- ❌ Don't store raw message_history as strings - use JSONB
- ❌ Don't skip structured logging for tool calls
- ❌ Don't hardcode model names - use settings

---

## Confidence Score: 8.0/10

**Strengths:**
- PydanticAI v1.x provides API stability guarantee (released Sept 2025)
- Clear FastAPI integration patterns with excellent documentation
- Existing service patterns from Registry/RAG/Backtesting to follow
- Tool integrations with existing modules well-defined
- Mock patterns established in RAG tests (mock_embedding_service)

**Risks:**
- WebSocket streaming with tools is complex
- LLM rate limits may affect integration tests
- Message history serialization edge cases
- Tool execution ordering in multi-step workflows

**Mitigations:**
- Pin PydanticAI version >=1.48.0 in pyproject.toml
- Comprehensive mocking following RAG test patterns
- Rate-limited integration tests with retry logic
- JSONB for flexible message storage
- Timeout handling with asyncio.wait_for

**Changes Since Initial Review (2026-02-01):**
- Updated PydanticAI from 0.1.0 to 1.48.0 (v1 stable)
- Updated Claude model identifier to claude-sonnet-4-5 format
- Added service method mapping notes to Task 7
- Added mock_pydantic_ai_agent fixture pattern
- Verified tool wrappers match actual service APIs

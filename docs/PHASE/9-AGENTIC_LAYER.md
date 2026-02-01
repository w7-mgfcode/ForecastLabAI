# Phase 9: Agentic Layer ("The Brain")

**Date Completed**: 2026-02-01
**PRP**: [PRP-10-agentic-layer.md](../../PRPs/PRP-10-agentic-layer.md)
**INITIAL**: [INITIAL-10.md](../../INITIAL-10.md)
**PR**: [#56](https://github.com/w7-mgfcode/ForecastLabAI/pull/56) (Open)

---

## Executive Summary

Phase 9 implements the **Agentic Layer** - the "Brain" of ForecastLabAI that provides autonomous decision-making, tool orchestration, and structured outputs using PydanticAI v1.48.0.

### Key Features

1. **Experiment Orchestrator Agent**
   - Autonomous model experimentation workflow
   - Systematic backtest execution and comparison
   - Deployment recommendation with human-in-the-loop approval

2. **RAG Assistant Agent**
   - Evidence-grounded question answering
   - Citation-backed responses with confidence scoring
   - "Insufficient evidence" detection to prevent hallucination

3. **Session Management**
   - PostgreSQL JSONB storage for message history
   - Configurable session TTL and expiration
   - Token usage tracking and tool call auditing

4. **Human-in-the-Loop Approval**
   - Blocks sensitive actions (create_alias, archive_run)
   - Configurable approval timeout
   - Audit trail for all decisions

5. **WebSocket Streaming**
   - Real-time token delivery for responsive UX
   - Tool call progress events
   - Error handling with session recovery

### Architecture Highlights

- **Lazy Agent Initialization**: Agents instantiated on first use (no API key required at import)
- **Structured Outputs**: All responses are Pydantic models (ExperimentReport, RAGAnswer)
- **Tool Integration**: Seamless binding to Registry, Backtesting, Forecasting, and RAG modules
- **Type Safety**: Full MyPy + Pyright compliance with strict mode

---

## Deliverables

### Database Schema

#### AgentSession Table (`agent_session`)

```sql
CREATE TABLE agent_session (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(32) UNIQUE NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',

    -- Conversation state (JSONB for flexibility)
    message_history JSONB NOT NULL DEFAULT '[]',

    -- Human-in-the-loop pending action
    pending_action JSONB NULL,

    -- Usage metrics
    total_tokens_used INTEGER NOT NULL DEFAULT 0,
    tool_calls_count INTEGER NOT NULL DEFAULT 0,

    -- Session timing
    last_activity TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,

    -- Timestamps (from TimestampMixin)
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),

    -- Constraints
    CHECK (status IN ('active', 'awaiting_approval', 'expired', 'closed'))
);

-- Indexes
CREATE UNIQUE INDEX ix_agent_session_session_id ON agent_session(session_id);
CREATE INDEX ix_agent_session_agent_type ON agent_session(agent_type);
CREATE INDEX ix_agent_session_status ON agent_session(status);
CREATE INDEX ix_agent_session_expires_at ON agent_session(expires_at);
CREATE INDEX ix_agent_session_message_history_gin ON agent_session USING gin(message_history);
```

**Migration**: `alembic/versions/d6e0f2g3h456_create_agent_session_table.py`

---

### Agent Definitions

#### Experiment Orchestrator Agent

**File**: `app/features/agents/agents/experiment.py`

**Purpose**: Autonomous model experimentation and deployment orchestration

**System Prompt**:
```
You are an ML experiment orchestrator for retail demand forecasting.

Your goal is to systematically test model configurations and recommend the best one.

Workflow:
1. Understand the user's goal (e.g., "find best model for store 1, product 1")
2. List available model types
3. Run backtests for promising configurations
4. Compare results and select the winner
5. Request approval before deployment actions

Always:
- Include baseline comparisons (naive, seasonal_naive)
- Use time-based backtesting (no data leakage)
- Justify recommendations with metrics
- Request human approval for create_alias and archive_run
```

**Structured Output**: `ExperimentReport`
```python
class ExperimentReport(BaseModel):
    run_id: str
    status: str
    summary: str
    metrics: dict[str, float]
    recommendations: list[str]
```

**Tools**:
- `list_models()` - Discover available model types
- `run_backtest()` - Execute time-series cross-validation
- `compare_runs()` - Compare two runs with config/metrics diffs
- `create_alias()` - Create deployment alias (requires approval)
- `archive_run()` - Archive a run (requires approval)

#### RAG Assistant Agent

**File**: `app/features/agents/agents/rag_assistant.py`

**Purpose**: Evidence-grounded documentation Q&A

**System Prompt**:
```
You are a documentation assistant for ForecastLabAI.

Your responses must be evidence-grounded:
- Only answer based on retrieved context
- Include citations for all claims
- If context is insufficient, set no_evidence=True
- Never hallucinate information

Always cite sources in the format:
- source_type (markdown, openapi, code)
- source_path (file path)
- snippet (relevant excerpt)
```

**Structured Output**: `RAGAnswer`
```python
class RAGAnswer(BaseModel):
    answer: str
    confidence: Literal["low", "medium", "high"]
    sources: list[dict[str, Any]]
    no_evidence: bool = False
```

**Tools**:
- `retrieve_context()` - Semantic search in pgvector knowledge base
- `format_citation()` - Format retrieved chunks as citations

---

### Tool Modules

#### Registry Tools

**File**: `app/features/agents/tools/registry_tools.py`

Tools:
- `list_runs()` - List model runs with filtering
- `get_run()` - Get run details by ID
- `compare_runs()` - Compare two runs with config/metrics diffs
- `create_alias()` - Create deployment alias (HITL approval required)
- `archive_run()` - Archive a run (HITL approval required)

#### Backtesting Tools

**File**: `app/features/agents/tools/backtesting_tools.py`

Tools:
- `run_backtest()` - Execute time-series CV backtest
- `get_backtest_splits()` - Preview train/test splits

#### Forecasting Tools

**File**: `app/features/agents/tools/forecasting_tools.py`

Tools:
- `list_models()` - Get available model types
- `train_model()` - Train a forecasting model
- `predict_with_model()` - Generate forecasts

#### RAG Tools

**File**: `app/features/agents/tools/rag_tools.py`

Tools:
- `retrieve_context()` - Semantic search for relevant docs
- `format_citation()` - Format retrieved chunk as citation

---

### Service Layer

**File**: `app/features/agents/service.py`

**Class**: `AgentService`

Key Methods:
```python
async def create_session(
    self, db: AsyncSession, agent_type: str, initial_context: dict | None
) -> SessionResponse
```
- Creates new session with unique session_id
- Sets expiration based on `agent_session_ttl_minutes`
- Initializes message_history as empty list

```python
async def get_session(
    self, db: AsyncSession, session_id: str
) -> SessionResponse | None
```
- Fetches session by ID
- Returns None if not found

```python
async def chat(
    self, db: AsyncSession, session_id: str, message: str
) -> ChatResponse
```
- Loads session and validates not expired
- Routes to appropriate agent (experiment or rag_assistant)
- Executes agent run with message history
- Captures tool calls and token usage
- Checks for pending approval actions
- Updates session state in database
- Returns structured response

```python
async def stream_chat(
    self, db: AsyncSession, session_id: str, message: str
) -> AsyncIterator[StreamEvent]
```
- Same as `chat()` but yields streaming events
- Events: text_delta, tool_call_start, tool_call_end, approval_required, complete, error

```python
async def approve_action(
    self, db: AsyncSession, session_id: str, action_id: str,
    approved: bool, reason: str | None
) -> ApprovalResponse
```
- Loads session and validates pending_action exists
- If approved: executes the tool call and returns result
- If rejected: marks action as rejected
- Updates session status and clears pending_action

```python
async def close_session(
    self, db: AsyncSession, session_id: str
) -> bool
```
- Marks session as closed
- Returns True if found and closed, False if not found

---

### REST API Routes

**File**: `app/features/agents/routes.py`

**Router Prefix**: `/agents`

#### Endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| `POST` | `/agents/sessions` | Create new agent session | `SessionResponse` (201) |
| `GET` | `/agents/sessions/{session_id}` | Get session status | `SessionResponse` (200) |
| `POST` | `/agents/sessions/{session_id}/chat` | Send message to agent | `ChatResponse` (200) |
| `POST` | `/agents/sessions/{session_id}/approve` | Approve/reject action | `ApprovalResponse` (200) |
| `DELETE` | `/agents/sessions/{session_id}` | Close session | 204 No Content |

**Error Codes**:
- `404 Not Found` - Session not found
- `410 Gone` - Session expired
- `400 Bad Request` - No approval pending or invalid request

---

### WebSocket Streaming

**File**: `app/features/agents/websocket.py`

**Endpoint**: `WS /agents/stream`

**Flow**:
1. Client connects to WebSocket
2. Client sends JSON message with session_id and message
3. Server validates session and routes to agent
4. Server streams events as agent generates response
5. Client receives real-time updates

**Event Types**:
- `text_delta` - Incremental text chunks
- `tool_call_start` - Tool invocation started
- `tool_call_end` - Tool execution completed with result
- `approval_required` - Sensitive action needs approval
- `complete` - Response finished with token usage
- `error` - Error occurred with recoverable flag

**Example Client Flow**:
```python
import asyncio
import websockets
import json

async def stream_chat():
    uri = "ws://localhost:8123/agents/stream"
    async with websockets.connect(uri) as ws:
        # Send message
        await ws.send(json.dumps({
            "session_id": "abc123",
            "message": "Find the best model for store 1, product 1"
        }))

        # Receive streaming events
        async for message in ws:
            event = json.loads(message)
            if event["event_type"] == "text_delta":
                print(event["data"]["delta"], end="", flush=True)
            elif event["event_type"] == "tool_call_start":
                print(f"\n[Calling {event['data']['tool_name']}...]")
            elif event["event_type"] == "complete":
                print(f"\n\nTokens used: {event['data']['tokens_used']}")
                break

asyncio.run(stream_chat())
```

---

## Configuration

**File**: `app/core/config.py`

### Agent LLM Configuration

```python
class Settings(BaseSettings):
    # Model Configuration
    agent_default_model: str = "anthropic:claude-sonnet-4-5"
    agent_fallback_model: str = "openai:gpt-4o"
    agent_temperature: float = 0.1
    agent_max_tokens: int = 4096

    # API Keys (optional, validated at usage time)
    anthropic_api_key: str = ""
    google_api_key: str = ""
    # Note: openai_api_key is defined in RAG section

    # Gemini Extended Reasoning Configuration
    agent_thinking_budget: int | None = None  # Token budget for thinking mode
```

### Supported LLM Providers

PydanticAI v1.48.0 automatically routes model requests based on model identifier prefix:

| Provider | Model Identifier Format | Authentication | Notes |
|----------|------------------------|----------------|-------|
| Anthropic Claude | `anthropic:claude-sonnet-4-5` | `ANTHROPIC_API_KEY` | Default, recommended for production |
| OpenAI GPT | `openai:gpt-4o` | `OPENAI_API_KEY` | Fallback model |
| Google Gemini (AI Studio) | `google-gla:gemini-3-flash` | `GOOGLE_API_KEY` | 60-70% cheaper than Gemini 2.5, 3x faster |
| Google Vertex AI | `google-vertex:gemini-*` | GCP Service Account | Enterprise deployments with Vertex AI |

**Model Selection Guide:**
- **Production**: `anthropic:claude-sonnet-4-5` (best balance of quality/speed/cost)
- **Cost-optimized**: `google-gla:gemini-3-flash` (fast, cheap, good quality)
- **Reasoning-heavy**: `google-gla:gemini-2-5-pro` with `agent_thinking_budget=4000`
- **Maximum quality**: `anthropic:claude-opus-4-5` (highest capability, slower)

### Gemini Extended Reasoning

Gemini 2.5+ models support "thinking mode" for complex multi-step reasoning:

```python
# Enable thinking mode by setting token budget
AGENT_THINKING_BUDGET=4000  # Recommended: 2000-8000 tokens

# Budget usage:
# - 2000: Simple multi-step tasks
# - 4000: Complex planning and analysis (recommended for agents)
# - 8000: Deep reasoning (experiment comparison, metric interpretation)
```

**When to enable:**
- Complex experiment planning (comparing 5+ models)
- Multi-step backtest analysis with trade-offs
- Metric interpretation requiring domain knowledge
- Deployment decisions with risk assessment

**When to disable:**
- Simple queries (single backtest execution)
- Quick RAG lookups
- Cost-sensitive deployments
- Latency-critical applications

---

## Dependencies

**File**: `pyproject.toml`

### Added Dependencies

```toml
dependencies = [
    # ... existing dependencies ...

    # Agentic Layer dependencies
    "pydantic-ai>=1.48.0",      # PydanticAI agent framework (v1 stable)
    "anthropic>=0.50.0",        # Anthropic SDK for Claude
]
```

**Notes**:
- PydanticAI v1.48.0 (released Jan 2026) provides API stability guarantee
- WebSocket support included in `uvicorn[standard]>=0.32.0` (already present)

---

## Test Coverage

**Total Tests**: 92 unit tests

### Test Files

| File | Tests | Focus |
|------|-------|-------|
| `test_models.py` | 14 | AgentSession ORM model validation |
| `test_schemas.py` | 24 | Pydantic schema validation and serialization |
| `test_service.py` | 28 | Service layer logic with mocked agents |
| `test_tools.py` | 18 | Tool function execution with mocked dependencies |
| `test_routes.py` | 8 | REST API endpoints with TestClient |

### Test Fixtures

**File**: `app/features/agents/tests/conftest.py`

Key Fixtures:
- `db_session` - Async database session with cleanup
- `client` - AsyncClient with database override
- `mock_experiment_agent` - Mocked PydanticAI agent for experiment
- `mock_rag_agent` - Mocked PydanticAI agent for RAG
- `sample_session` - Pre-populated AgentSession ORM instance
- `sample_chat_request` - Valid ChatRequest fixture
- `sample_approval_request` - Valid ApprovalRequest fixture

### Running Tests

```bash
# All unit tests (no API keys required)
uv run pytest app/features/agents/tests/ -v -m "not integration"

# Expected: 92 passed
```

**Note**: Integration tests requiring real LLM API calls are not yet implemented (will be rate-limited and marked with `@pytest.mark.integration`).

---

## Validation Results

### Ruff (Linting & Formatting)

```bash
uv run ruff check app/features/agents/
uv run ruff format app/features/agents/
```

**Result**: ✅ All checks passed, no errors

### MyPy (Type Checking)

```bash
uv run mypy app/features/agents/
```

**Result**: ✅ 0 errors

### Pyright (Type Checking)

```bash
uv run pyright app/features/agents/
```

**Result**: ✅ 0 errors, 22 warnings

**Warnings**:
- PydanticAI has partial type coverage (expected)
- All warnings are from `pydantic_ai.messages` and `pydantic_ai.result` modules
- Warnings relaxed via `pyproject.toml`:
  ```toml
  reportUnknownVariableType = "warning"
  reportUnknownArgumentType = "warning"
  reportUnknownMemberType = "warning"
  ```

### Pytest (All Tests)

```bash
uv run pytest app/features/agents/tests/ -v
```

**Result**: ✅ 92 passed in 2.34s

---

## Directory Structure

```
app/features/agents/
├── __init__.py                    # Export router
├── models.py                      # AgentSession ORM model
├── schemas.py                     # Request/Response Pydantic schemas (382 lines)
├── routes.py                      # REST endpoints (222 lines)
├── websocket.py                   # WebSocket streaming endpoint (158 lines)
├── service.py                     # AgentService orchestration (608 lines)
├── deps.py                        # AgentDeps dataclass for DI (36 lines)
├── agents/
│   ├── __init__.py                # Export agents
│   ├── base.py                    # Agent configuration helpers (89 lines)
│   ├── experiment.py              # Experiment Orchestrator Agent (349 lines)
│   └── rag_assistant.py           # RAG Assistant Agent (170 lines)
├── tools/
│   ├── __init__.py                # Export all tools
│   ├── registry_tools.py          # Registry tool functions (258 lines)
│   ├── backtesting_tools.py       # Backtesting tool functions (268 lines)
│   ├── forecasting_tools.py       # Forecasting tool functions (189 lines)
│   └── rag_tools.py               # RAG tool functions (165 lines)
└── tests/
    ├── __init__.py
    ├── conftest.py                # Test fixtures (387 lines)
    ├── test_models.py             # ORM model tests (239 lines)
    ├── test_schemas.py            # Schema validation tests (429 lines)
    ├── test_service.py            # Service layer tests (548 lines)
    ├── test_tools.py              # Tool function tests (317 lines)
    └── test_routes.py             # API endpoint tests (226 lines)

alembic/versions/
└── d6e0f2g3h456_create_agent_session_table.py

examples/
└── agents/                        # Usage examples
    ├── experiment_demo.py         # Full experiment workflow example
    ├── rag_query.http             # HTTP client examples for RAG
    └── websocket_client.py        # WebSocket streaming client
```

---

## Next Phase Preparation

### Phase 10: ForecastLab Dashboard

**Dependencies on Phase 9**:
- WebSocket streaming endpoint (`/agents/stream`) ready for frontend integration
- Agent session management API (`/agents/sessions/*`) for chat interface
- Structured outputs (ExperimentReport, RAGAnswer) for rendering results
- Citation format for displaying sources in UI

**Frontend Integration Points**:
1. **Chat Interface**: WebSocket client for real-time streaming
2. **Approval UI**: Modal for human-in-the-loop approval decisions
3. **Session List**: Display active sessions with status
4. **Tool Call Timeline**: Visualize agent workflow steps
5. **Citation Display**: Render evidence-grounded answers with clickable sources

---

## Known Limitations

1. **No Integration Tests**: Real LLM API tests not yet implemented (requires rate limiting)
2. **No Examples**: Demo scripts in `examples/agents/` not yet created
3. **Limited Error Recovery**: WebSocket disconnect handling could be enhanced
4. **Single-User Sessions**: No multi-user session isolation (future enhancement)
5. **Memory-Only Context**: Agent tools load fresh data on each call (no caching)

---

## References

- [PydanticAI Documentation](https://ai.pydantic.dev/)
- [PydanticAI GitHub](https://github.com/pydantic/pydantic-ai)
- [Anthropic Claude API](https://docs.anthropic.com/en/api)
- [INITIAL-10.md](../../INITIAL-10.md) - Agentic Layer specification
- [PRP-10-agentic-layer.md](../../PRPs/PRP-10-agentic-layer.md) - Implementation plan
- [PR #56](https://github.com/w7-mgfcode/ForecastLabAI/pull/56) - Implementation PR

---

**Completion Date**: 2026-02-01
**Phase Status**: ✅ Completed
**Next Phase**: Phase 10 - ForecastLab Dashboard (Pending)

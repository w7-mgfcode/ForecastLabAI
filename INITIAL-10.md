# INITIAL-10.md — Agentic Layer (The Brain)

## Architectural Role

**"The Brain"** - Autonomous decision-making, tool orchestration, and structured outputs using PydanticAI.

This phase provides intelligent orchestration capabilities:
- Experiment automation (config generation → backtest → deploy)
- RAG-powered Q&A with evidence-grounded answers and citations
- Human-in-the-loop approval for sensitive operations
- Structured, schema-enforced outputs

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Agent Framework | [PydanticAI](https://ai.pydantic.dev/) | Type-safe agent orchestration |
| Tool System | [Function Tools](https://ai.pydantic.dev/tools/) | API binding |
| Tool Groups | [Toolsets](https://ai.pydantic.dev/toolsets/) | Grouped tool management |
| LLM Provider | Anthropic Claude / OpenAI GPT-4 | Configurable provider |
| Streaming | [PydanticAI Streaming](https://ai.pydantic.dev/results/#streamed-results) | Real-time responses |

---

## FEATURE

### Experiment Orchestrator Agent
Autonomous experiment workflow management:
- **Tools**: `list_models`, `run_backtest`, `compare_runs`, `create_alias`, `archive_run`
- **Workflow**: Generate configs → Run backtests → Analyze metrics → Select best → Deploy alias
- **Output**: Structured `ExperimentReport` with methodology, results, and recommendations

### RAG Assistant Agent
Evidence-grounded question answering:
- **Tools**: `retrieve_context` (from INITIAL-9), `format_citation`
- **Workflow**: Parse query → Retrieve chunks → Synthesize answer → Format citations
- **Output**: Structured `RAGResponse` with answer, citations, and confidence score

### Agent Session Management
- Session state persistence for multi-turn conversations
- Tool call logging with correlation IDs
- Human-in-the-loop approval for sensitive actions
- Graceful LLM API failure handling with retries

---

## ENDPOINTS

### POST /agents/experiment/run
Execute an experiment workflow with the Orchestrator Agent.

**Request**:
```json
{
  "objective": "Find the best model configuration for store S001, product P001",
  "constraints": {
    "model_types": ["moving_average", "seasonal_naive"],
    "min_train_size": 60,
    "max_splits": 5
  },
  "auto_deploy": false,
  "session_id": "optional-session-id"
}
```

**Response**:
```json
{
  "session_id": "sess_abc123",
  "status": "completed",
  "report": {
    "objective": "Find the best model configuration for store S001, product P001",
    "methodology": "Evaluated 6 configurations using 5-fold expanding window CV",
    "experiments_run": 6,
    "best_run": {
      "run_id": "run_xyz789",
      "model_type": "moving_average",
      "config": {"window": 14},
      "metrics": {
        "mae": 12.5,
        "smape": 15.2,
        "wape": 0.08
      }
    },
    "baseline_comparison": {
      "vs_naive": {
        "mae_improvement_pct": 23.5,
        "smape_improvement_pct": 18.2
      }
    },
    "recommendation": "Deploy moving_average with window=14",
    "approval_required": true,
    "pending_action": "create_alias"
  },
  "tool_calls": [
    {
      "tool": "list_models",
      "args": {},
      "result_summary": "Found 4 model types"
    },
    {
      "tool": "run_backtest",
      "args": {"model_type": "moving_average", "window": 7},
      "result_summary": "MAE: 15.2"
    }
  ],
  "tokens_used": 2450,
  "duration_ms": 45000
}
```

### POST /agents/experiment/approve
Approve a pending action from an experiment session.

**Request**:
```json
{
  "session_id": "sess_abc123",
  "action": "create_alias",
  "approved": true,
  "comment": "Approved for staging deployment"
}
```

**Response**:
```json
{
  "session_id": "sess_abc123",
  "action": "create_alias",
  "status": "executed",
  "result": {
    "alias_name": "production",
    "run_id": "run_xyz789"
  }
}
```

### POST /agents/rag/query
Query with answer generation using the RAG Assistant Agent.

**Request**:
```json
{
  "query": "How does the backtesting module prevent data leakage?",
  "session_id": "optional-session-id",
  "include_sources": true
}
```

**Response**:
```json
{
  "session_id": "sess_def456",
  "answer": "The backtesting module prevents data leakage through several mechanisms:\n\n1. **Time-based splits only**: The TimeSeriesSplitter uses expanding or sliding window strategies, never random splits.\n\n2. **Gap parameter**: Configurable gap between train and test sets simulates operational latency.\n\n3. **Lag feature validation**: Features are computed with explicit cutoff dates to prevent future data access.",
  "confidence": 0.92,
  "citations": [
    {
      "source_type": "markdown",
      "source_path": "docs/PHASE/5-BACKTESTING.md",
      "chunk_id": "chunk_abc123",
      "snippet": "TimeSeriesSplitter uses time-based splits (expanding/sliding window)...",
      "relevance_score": 0.94
    },
    {
      "source_type": "markdown",
      "source_path": "CLAUDE.md",
      "chunk_id": "chunk_def456",
      "snippet": "Backtesting uses time-based splits (rolling/expanding), never random split...",
      "relevance_score": 0.89
    }
  ],
  "tokens_used": 1250,
  "duration_ms": 3200
}
```

### GET /agents/status/{session_id}
Check agent session status.

**Response**:
```json
{
  "session_id": "sess_abc123",
  "agent_type": "experiment_orchestrator",
  "status": "awaiting_approval",
  "created_at": "2026-02-01T10:30:00Z",
  "last_activity": "2026-02-01T10:35:00Z",
  "pending_action": {
    "action": "create_alias",
    "details": {
      "alias_name": "production",
      "run_id": "run_xyz789"
    }
  },
  "tool_calls_count": 8,
  "tokens_used": 2450
}
```

### WS /agents/stream
WebSocket endpoint for streaming responses.

**Client → Server**:
```json
{
  "type": "query",
  "agent": "rag_assistant",
  "payload": {
    "query": "Explain the model registry workflow"
  }
}
```

**Server → Client (streaming)**:
```json
{"type": "token", "content": "The"}
{"type": "token", "content": " model"}
{"type": "token", "content": " registry"}
{"type": "tool_call", "tool": "retrieve_context", "status": "started"}
{"type": "tool_call", "tool": "retrieve_context", "status": "completed", "summary": "Found 5 relevant chunks"}
{"type": "token", "content": " tracks..."}
{"type": "complete", "session_id": "sess_xyz", "tokens_used": 850}
```

---

## AGENT DEFINITIONS

### Experiment Orchestrator Agent

```python
from pydantic_ai import Agent
from pydantic import BaseModel

class ExperimentReport(BaseModel):
    """Structured output for experiment results."""
    objective: str
    methodology: str
    experiments_run: int
    best_run: RunSummary
    baseline_comparison: BaselineComparison
    recommendation: str
    approval_required: bool
    pending_action: str | None

experiment_agent = Agent(
    model="anthropic:claude-sonnet-4-20250514",
    result_type=ExperimentReport,
    system_prompt="""You are an ML experiment orchestrator for retail demand forecasting.

Your goal is to find the best model configuration through systematic experimentation.
Always:
1. Start with baseline models (naive, seasonal_naive)
2. Compare against baselines with improvement percentages
3. Use time-based backtesting with appropriate train/test splits
4. Recommend the best configuration with justification
5. Request approval before deployment actions""",
    tools=[list_models, run_backtest, compare_runs, create_alias, archive_run]
)
```

### RAG Assistant Agent

```python
class RAGResponse(BaseModel):
    """Structured output for RAG queries."""
    answer: str
    confidence: float  # 0.0 - 1.0
    citations: list[Citation]
    insufficient_context: bool = False

rag_agent = Agent(
    model="anthropic:claude-sonnet-4-20250514",
    result_type=RAGResponse,
    system_prompt="""You are a documentation assistant for ForecastLabAI.

Your responses must be evidence-grounded:
- Only answer based on retrieved context
- Include citations for all claims
- If context is insufficient, set insufficient_context=True and explain what's missing
- Never hallucinate information not in the retrieved chunks""",
    tools=[retrieve_context, format_citation]
)
```

---

## TOOL DEFINITIONS

### list_models
```python
@tool
async def list_models(ctx: RunContext[AgentDeps]) -> list[ModelInfo]:
    """List available forecasting models with their configurations.

    Use this to discover what model types can be experimented with.
    Returns model_type, default_config, and description.
    """
    ...
```

### run_backtest
```python
@tool
async def run_backtest(
    ctx: RunContext[AgentDeps],
    model_type: str,
    config: dict[str, Any],
    store_id: str,
    product_id: str,
    n_splits: int = 5
) -> BacktestResult:
    """Run a backtest for a model configuration.

    Use this to evaluate model performance with time-series CV.
    Returns per-fold and aggregated metrics (MAE, sMAPE, WAPE).
    """
    ...
```

### retrieve_context
```python
@tool
async def retrieve_context(
    ctx: RunContext[AgentDeps],
    query: str,
    top_k: int = 5
) -> list[RetrievedChunk]:
    """Retrieve relevant documentation chunks for a query.

    Use this before answering any question about the system.
    Returns chunks with content, source_path, and relevance_score.
    """
    ...
```

---

## CONFIGURATION (Settings)

```python
# app/core/config.py additions

# Agent LLM Configuration
agent_default_model: str = "anthropic:claude-sonnet-4-20250514"
agent_fallback_model: str = "openai:gpt-4o"
agent_temperature: float = 0.1
agent_max_tokens: int = 4096

# Agent Execution Configuration
agent_max_tool_calls: int = 10
agent_timeout_seconds: int = 120
agent_retry_attempts: int = 3
agent_retry_delay_seconds: float = 1.0

# Human-in-the-Loop Configuration
agent_require_approval: list[str] = ["create_alias", "archive_run"]
agent_approval_timeout_minutes: int = 60

# Streaming Configuration
agent_enable_streaming: bool = True
agent_stream_chunk_size: int = 10  # tokens per chunk

# Session Configuration
agent_session_ttl_minutes: int = 120
agent_max_sessions_per_user: int = 5
```

---

## SUCCESS CRITERIA

- [ ] Agents produce schema-enforced structured outputs
- [ ] Tool calls are logged with correlation IDs and timing
- [ ] Human-in-the-loop approval blocks sensitive actions
- [ ] Graceful handling of LLM API failures with retries
- [ ] WebSocket streaming delivers tokens in real-time
- [ ] Session state persists across multiple requests
- [ ] Unit tests with mocked LLM responses
- [ ] Integration tests with real LLM calls (rate-limited)
- [ ] Structured logging for all agent operations
- [ ] Token usage tracked per session for cost monitoring

---

## CROSS-MODULE INTEGRATION

| Direction | Module | Integration Point |
|-----------|--------|-------------------|
| **← RAG Layer** | INITIAL-9 | Uses `retrieve_context` tool |
| **← Registry** | Phase 6 | Uses `list_runs`, `compare_runs`, `create_alias` tools |
| **← Backtesting** | Phase 5 | Uses `run_backtest` tool |
| **← Forecasting** | Phase 4 | Uses `list_models`, `train_model` tools |
| **→ Dashboard** | INITIAL-11 | Provides chat interface backend |
| **→ Jobs** | Phase 7 | Creates job records for audit trail |

---

## DOCUMENTATION LINKS

- [PydanticAI Documentation](https://ai.pydantic.dev/)
- [PydanticAI Agents](https://ai.pydantic.dev/agents/)
- [PydanticAI Tools](https://ai.pydantic.dev/tools/)
- [PydanticAI Toolsets](https://ai.pydantic.dev/toolsets/)
- [PydanticAI Built-in Tools](https://ai.pydantic.dev/builtin-tools/)
- [PydanticAI Streaming Results](https://ai.pydantic.dev/results/#streamed-results)
- [PydanticAI GitHub](https://github.com/pydantic/pydantic-ai)
- [Anthropic Claude API](https://docs.anthropic.com/en/api)

---

## OTHER CONSIDERATIONS

- **Structured Outputs**: All agent responses are Pydantic models, never raw text
- **Tool Docstrings**: Follow guidance in CLAUDE.md for agent-optimized tool documentation
- **Cost Control**: Track and limit token usage per session
- **Audit Trail**: All tool calls logged with request correlation for debugging
- **Fallback Provider**: Automatic failover to fallback model on primary failure
- **Approval Workflow**: Pending actions expire after `agent_approval_timeout_minutes`

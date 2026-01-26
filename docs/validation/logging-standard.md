# Logging Standard: Hybrid Dotted Namespace Pattern

## Format Specification

**Pattern:** `{domain}.{component}.{action}_{state}`

Where:
- **domain**: Top-level category (application, request, database, agent, external, system)
- **component**: Subsystem or feature (lifecycle, http, connection, tool, llm, etc.)
- **action_state**: Descriptive operation with state using snake_case

**Examples:**
- `application.lifecycle.started`
- `request.http_received`
- `database.connection_initialized`
- `agent.tool.execution_started`

## Why This Pattern?

Based on comprehensive research of OpenTelemetry standards and AI agent frameworks (2024-2025):

1. **OpenTelemetry Compliant** - Follows official semantic conventions
2. **Scalable Hierarchy** - Supports multi-level event taxonomies
3. **Grep-Friendly** - Easy to search with `grep "database\."` or `grep "_failed"`
4. **AI-Parseable** - Clear hierarchical relationships for LLM understanding
5. **State Machine Tracking** - Natural expression of lifecycle transitions
6. **Industry Standard** - Matches Elastic, OTel, LangChain, AWS patterns

## Event Taxonomy

### Application Domain

Application-level lifecycle and system events.

```
application.
├── lifecycle.started          # Application started successfully
├── lifecycle.stopped          # Application shut down gracefully
├── lifecycle.restarting       # Application restarting
├── config.loaded              # Configuration loaded successfully
├── config.validation_failed   # Configuration validation error
└── initialization_failed      # Fatal startup error
```

**Examples:**
```python
logger.info("application.lifecycle.started",
           app_name=settings.app_name,
           version=settings.version,
           environment=settings.environment)

logger.error("application.config.validation_failed",
            error="Invalid DATABASE_URL format",
            exc_info=True)
```

### Request Domain

HTTP request/response lifecycle tracking.

```
request.
├── http_received              # Request received (use instead of "started")
├── http_processing            # Request being processed
├── http_completed             # Request completed successfully
├── http_failed                # Request failed with error
├── validation_failed          # Request validation error
├── rate_limited               # Rate limit exceeded
└── timeout_exceeded           # Request timeout
```

**Examples:**
```python
logger.info("request.http_received",
           method=request.method,
           path=request.url.path,
           client_host=request.client.host)

logger.info("request.http_completed",
           method=request.method,
           path=request.url.path,
           status_code=response.status_code,
           duration_ms=duration)

logger.error("request.http_failed",
            method=request.method,
            path=request.url.path,
            error=str(e),
            duration_ms=duration,
            exc_info=True)
```

### Database Domain

Database operations and health monitoring.

```
database.
├── connection_initialized     # Connection pool initialized
├── connection_established     # Single connection established
├── connection_closed          # Connection closed
├── connection_failed          # Connection failed
├── query_executed             # Query executed successfully
├── query_failed               # Query execution failed
├── transaction_started        # Transaction begun
├── transaction_committed      # Transaction committed
├── transaction_rolled_back    # Transaction rolled back
├── migration_started          # Migration started
├── migration_completed        # Migration completed
├── migration_failed           # Migration failed
├── health_check_passed        # Health check successful
└── health_check_failed        # Health check failed
```

**Examples:**
```python
logger.info("database.connection_initialized",
           pool_size=5,
           max_overflow=10,
           provider="postgresql")

logger.error("database.health_check_failed",
            provider="postgresql",
            exc_info=True)

logger.info("database.query_executed",
           query_type="SELECT",
           table="users",
           duration_ms=45.2)
```

### Health Domain

Health check and readiness monitoring.

```
health.
├── check_passed               # Generic health check passed
├── check_failed               # Generic health check failed
├── readiness_check_passed     # Readiness check passed
├── readiness_check_failed     # Readiness check failed
├── liveness_check_passed      # Liveness check passed
└── liveness_check_failed      # Liveness check failed
```

**Examples:**
```python
logger.info("health.readiness_check_passed",
           database="connected",
           cache="connected",
           environment=settings.environment)

logger.error("health.readiness_check_failed",
            component="database",
            reason="connection timeout",
            exc_info=True)
```

### Agent Domain (For Future AI Agent Features)

Agent operations, planning, and tool execution.

```
agent.
├── lifecycle.initialized      # Agent initialized
├── lifecycle.started          # Agent execution started
├── lifecycle.stopped          # Agent execution stopped
├── planning.initiated         # Planning phase started
├── planning.step_completed    # Planning step completed
├── planning.completed         # Planning completed
├── planning.failed            # Planning failed
├── tool.
│   ├── selection_started      # Tool selection initiated
│   ├── selection_evaluated    # Tool evaluated for suitability
│   ├── selection_chosen       # Tool chosen
│   ├── validation_checking    # Validating tool inputs
│   ├── validation_passed      # Tool inputs valid
│   ├── validation_failed      # Tool inputs invalid
│   ├── execution_started      # Tool execution began
│   ├── execution_progress     # Tool execution progress update
│   ├── execution_completed    # Tool finished successfully
│   ├── execution_failed       # Tool execution failed
│   ├── result_parsing         # Parsing tool output
│   ├── result_validated       # Output validated
│   └── result_stored          # Result saved to context
├── llm.
│   ├── call_started           # LLM API call initiated
│   ├── streaming_started      # Streaming response started
│   ├── chunk_received         # Stream chunk received
│   ├── streaming_completed    # Streaming finished
│   ├── call_completed         # LLM call completed
│   ├── call_failed            # LLM call failed
│   ├── token_usage_recorded   # Token usage tracked
│   └── rate_limit_exceeded    # Rate limit hit
├── memory.
│   ├── storage_written        # Data written to memory
│   ├── storage_read           # Data read from memory
│   ├── storage_cleared        # Memory cleared
│   ├── retrieval_queried      # Memory query initiated
│   ├── retrieval_found        # Memory item found
│   └── retrieval_not_found    # Memory item not found
└── self_correction.
    ├── initiated              # Self-correction started
    ├── strategy_selected      # Correction strategy chosen
    ├── retry_attempted        # Retry attempt
    ├── completed              # Self-correction successful
    └── failed                 # Self-correction failed
```

**Examples:**
```python
logger.info("agent.tool.execution_started",
           tool="web_search",
           query="AI observability patterns",
           timeout=30)

logger.info("agent.llm.call_completed",
           model="claude-3-opus",
           tokens_prompt=1500,
           tokens_completion=800,
           cost_usd=0.0345,
           duration_ms=2341)

logger.error("agent.tool.execution_failed",
            tool="web_search",
            error="API rate limit exceeded",
            retry_count=2,
            retryable=True,
            exc_info=True)
```

### External Domain

External API calls and third-party service interactions.

```
external.
├── api.call_started           # External API call started
├── api.call_completed         # API call completed
├── api.call_failed            # API call failed
├── api.rate_limited           # External rate limit hit
├── webhook.received           # Webhook received
├── webhook.processed          # Webhook processed
└── webhook.failed             # Webhook processing failed
```

**Examples:**
```python
logger.info("external.api.call_completed",
           provider="openai",
           endpoint="/v1/chat/completions",
           status=200,
           duration_ms=1245.5)

logger.error("external.api.call_failed",
            provider="stripe",
            endpoint="/v1/charges",
            status=503,
            retry_attempt=1,
            exc_info=True)
```

### Feature Domains (Examples)

For feature-specific logging, use the feature name as domain.

```
user.
├── registration_started       # User registration initiated
├── registration_completed     # User registered successfully
├── registration_failed        # Registration failed
├── login_started              # Login attempt
├── login_completed            # Login successful
├── login_failed               # Login failed
├── password_reset_requested   # Password reset requested
└── account_deleted            # Account deletion completed

product.
├── create_started             # Product creation started
├── create_completed           # Product created
├── create_failed              # Product creation failed
├── update_started             # Product update started
├── update_completed           # Product updated
└── delete_completed           # Product deleted

order.
├── process_started            # Order processing started
├── payment_completed          # Payment processed
├── fulfillment_started        # Fulfillment initiated
├── process_completed          # Order completed
└── process_failed             # Order processing failed
```

## Standard States

Use these standard state suffixes consistently:

| State | Usage | Example |
|-------|-------|---------|
| `_started` | Operation initiated | `tool.execution_started` |
| `_progress` | Operation in progress | `tool.execution_progress` |
| `_completed` | Operation successful | `tool.execution_completed` |
| `_failed` | Operation failed | `tool.execution_failed` |
| `_validated` | Validation successful | `input.validation_validated` |
| `_rejected` | Validation failed | `input.validation_rejected` |
| `_retrying` | Retry attempt | `api.call_retrying` |
| `_cancelled` | Operation cancelled | `request.http_cancelled` |
| `_timeout` | Operation timed out | `request.http_timeout` |
| `_received` | Event received | `request.http_received` |
| `_sent` | Event sent | `notification.email_sent` |

## Depth Guidelines

- **Level 1 (Domain):** Broad system category - `agent`, `request`, `database`
- **Level 2 (Component):** Specific subsystem - `tool`, `llm`, `http`
- **Level 3 (Operation):** Detailed action - `execution_started`, `call_completed`
- **Level 4 (Optional):** Sub-operation - `agent.tool.web_search.execution_started`

**Maximum recommended depth:** 4 levels
**Minimum recommended depth:** 3 levels (domain.component.action_state)

## Required Log Attributes

Always include these context fields:

### All Logs
- `timestamp` - ISO 8601 timestamp (automatic)
- `level` - Log level (automatic)
- `request_id` - Request correlation ID (automatic via middleware)

### Application Logs
- `app_name` - Application name
- `version` - Application version
- `environment` - Environment (development/staging/production)

### Request Logs
- `method` - HTTP method
- `path` - Request path
- `status_code` - Response status
- `duration_ms` - Request duration in milliseconds
- `client_host` - Client IP/host

### Database Logs
- `provider` - Database provider (postgresql, mysql, etc.)
- `duration_ms` - Query duration
- `pool_size` - Connection pool size (when relevant)

### Error Logs
- `error` - Error message
- `error_type` - Error class name
- `exc_info` - Set to `True` for stack traces
- `retryable` - Whether error is retryable (boolean)
- `retry_count` - Number of retry attempts

### Agent Logs
- `agent_id` - Agent instance ID
- `run_id` - Execution run ID
- `tool` - Tool name
- `model` - LLM model name
- `tokens_prompt` - Prompt token count
- `tokens_completion` - Completion token count
- `cost_usd` - Estimated cost

## Usage Examples

### Basic Logging Pattern

```python
from app.core.logging import get_logger

logger = get_logger(__name__)

# Simple event
logger.info("user.registration_started", email=email, source="web")

# With duration tracking
import time
start = time.time()
# ... do work ...
duration_ms = (time.time() - start) * 1000
logger.info("user.registration_completed",
           email=email,
           user_id=user.id,
           duration_ms=round(duration_ms, 2))

# Error logging
try:
    result = perform_operation()
except ValueError as e:
    logger.error("operation.validation_failed",
                error=str(e),
                error_type="ValueError",
                input_value=value,
                exc_info=True)  # Include stack trace
    raise
```

### Lifecycle Pattern

```python
# Start
logger.info("process.execution_started", process_id=id, params=params)

try:
    # Progress updates
    logger.info("process.execution_progress",
               process_id=id,
               step=1,
               total_steps=5)

    # Success
    result = execute()
    logger.info("process.execution_completed",
               process_id=id,
               result_count=len(result),
               duration_ms=duration)

except Exception as e:
    # Failure
    logger.error("process.execution_failed",
                process_id=id,
                error=str(e),
                error_type=type(e).__name__,
                retryable=is_retryable(e),
                exc_info=True)
    raise
```

### Correlation Pattern

```python
# Use request_id for correlation (automatic in middleware)
logger.info("request.http_received", method="POST", path="/api/orders")
logger.info("order.process_started", order_id=123)
logger.info("order.payment_completed", order_id=123, amount=99.99)
logger.info("order.process_completed", order_id=123)
logger.info("request.http_completed", status_code=201)

# All logs will have the same request_id automatically
```

## Query Patterns

### Grep Examples

```bash
# All agent events
grep '"event":"agent\.' logs.json

# All tool operations
grep '"event":"agent\.tool\.' logs.json

# Failed events across system
grep '_failed"' logs.json

# Specific request trace
grep '"request_id":"req-789"' logs.json | jq -r '.event'

# Performance issues (>1000ms)
grep 'duration_ms' logs.json | jq 'select(.duration_ms > 1000)'

# All database errors
grep '"event":"database\.' logs.json | grep '"level":"error"'
```

### Analysis with jq

```bash
# Count events by type
cat logs.json | jq -r '.event' | sort | uniq -c | sort -rn

# Average duration by endpoint
cat logs.json | jq -s 'group_by(.path) | map({path: .[0].path, avg_duration: (map(.duration_ms) | add / length)})'

# Error rate by domain
cat logs.json | jq -r 'select(.level == "error") | .event' | cut -d'.' -f1 | sort | uniq -c
```

## Migration from Old Pattern

### Old Pattern (feature.action.status)
```python
logger.info("request.started")
logger.info("product.create.completed")
logger.error("database.health_check.failed")
```

### New Pattern (domain.component.action_state)
```python
logger.info("request.http_received")
logger.info("product.create_completed")
logger.error("database.health_check_failed")
```

### Key Changes
1. **Underscores in final segment**: `.completed` → `_completed`
2. **Specific component names**: `request.*` → `request.http_*`
3. **Descriptive actions**: `started` → `received`, `initialized`, etc.
4. **Consistent depth**: Minimum 3 levels (domain.component.action_state)

## Do's and Don'ts

### ✅ DO
- Use structured logging with keyword arguments
- Include context (IDs, values, durations)
- Log lifecycle events (started, completed, failed)
- Use `exc_info=True` for errors
- Follow the naming taxonomy
- Include performance metrics (duration_ms)
- Log business-relevant events

### ❌ DON'T
- Use string formatting or f-strings in event names
- Log sensitive data (passwords, tokens, PII)
- Spam logs in tight loops (aggregate instead)
- Use vague event names ("processing", "handling")
- Mix naming patterns
- Skip error context
- Log at wrong levels (debug vs info vs error)
- Create deep hierarchies (>4 levels)

## Type Annotations

All logging calls should use proper type hints:

```python
from typing import Any
import structlog
from structlog.typing import WrappedLogger

logger: WrappedLogger = get_logger(__name__)

def process_user(user_id: int, email: str) -> None:
    logger.info("user.process_started", user_id=user_id, email=email)
    # ... processing ...
    logger.info("user.process_completed", user_id=user_id)
```

## Testing Logging

```python
import json
from io import StringIO
import pytest

def test_logging_event_format(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that logging follows hybrid pattern."""
    logger = get_logger("test")

    logger.info("user.registration_started", email="test@example.com")

    captured = capsys.readouterr()
    log_data = json.loads(captured.out.strip())

    # Verify format
    assert log_data["event"] == "user.registration_started"
    assert "." in log_data["event"]  # Contains dots
    assert "_" in log_data["event"]  # Contains underscores
    assert log_data["email"] == "test@example.com"
    assert "timestamp" in log_data
    assert log_data["level"] == "info"
```

## References

- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/concepts/semantic-conventions/)
- [Structlog Documentation](https://www.structlog.org/)
- [LangChain Observability](https://python.langchain.com/docs/guides/productionization/logging)
- Research: AI Agent Feedback Loop Optimization (2024-2025)

---

**Last Updated:** 2025-10-29
**Version:** 1.0.0

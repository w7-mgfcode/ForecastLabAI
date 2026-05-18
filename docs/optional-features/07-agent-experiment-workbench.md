# Agent Experiment Workbench

## Summary

Turn agent-driven experimentation into an inspectable workbench with plans, tool traces, approvals, results, and rollback paths. The current chat page can start RAG or experiment sessions, but agent work is not yet presented as a structured experiment artifact.

## Why It Fits ForecastLabAI

ForecastLabAI already has:

- PydanticAI agents.
- Session management.
- Tool calls.
- Human-in-the-loop approval.
- Registry and backtesting tools.
- Chat UI and Agent Guide.

The workbench makes agent behavior auditable and product-grade.

## User Value

- Users can trust what the agent did and why.
- Sensitive actions remain approval-gated.
- Experiment runs become reproducible.
- Demo reviewers can see agent autonomy without losing control.

## Proposed UX

Create `/agents/workbench` or extend `/chat`.

Sections:

- Session list.
- Current plan.
- Tool timeline.
- Pending approval cards.
- Metrics comparison.
- Recommended action.
- Final report.
- Links to runs, jobs, aliases, and backtests.

## Backend Design

Extend agent session persistence:

- Store structured plan.
- Store tool call events.
- Store approval decisions.
- Store final experiment report.

Candidate endpoints:

- `GET /agents/sessions`
- `GET /agents/sessions/{session_id}/events`
- `GET /agents/sessions/{session_id}/report`

## MVP Scope

- Read-only session detail page.
- Tool call timeline.
- Pending approval UI reuse.
- Final response/report display.

## Full Version

- Agent-generated experiment plans before execution.
- User-editable plan steps.
- Run comparison embedded in workbench.
- Rollback/archive workflow.
- Exportable experiment report.

## Risks

- Tool traces can leak sensitive parameters if not filtered.
- Agent UX can become confusing if chat and workbench diverge.
- Approval state must remain strongly consistent with backend session status.

## Validation Plan

- Unit tests for event serialization.
- API tests for session/event/report retrieval.
- Browser QA for active, completed, awaiting-approval, expired, and closed sessions.
- Security review for secret redaction in tool traces.

## Documentation

- Pydantic AI documentation: https://ai.pydantic.dev/
- Pydantic AI overview: https://pydantic.dev/docs/ai/overview/
- Pydantic AI models documentation: https://pydantic.dev/docs/ai/models/overview/
- Pydantic AI capabilities: https://pydantic.dev/docs/ai/core-concepts/capabilities/
- FastAPI WebSockets: https://fastapi.tiangolo.com/advanced/websockets/
- Pydantic documentation: https://docs.pydantic.dev/latest/
- OWASP Top 10 for LLM Applications: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework
- TanStack Query React documentation: https://tanstack.com/query/latest/docs/framework/react/overview
- Radix UI primitives documentation: https://www.radix-ui.com/primitives/docs

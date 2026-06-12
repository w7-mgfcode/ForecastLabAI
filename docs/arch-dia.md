# ForecastLabAI Architecture Diagrams

This document provides diagram-first views of the repository's logic, workflows, stack, APIs, architecture, and reusable patterns. The diagrams are grounded in the inspected code under `app/`, `frontend/src/`, `docker-compose.yml`, and the base docs.

## 1. System context

```mermaid
flowchart LR
    User[User or Reviewer]
    UI[React SPA<br/>Vite + React Query + Router]
    API[FastAPI App<br/>app/main.py]
    DB[(PostgreSQL 16 + pgvector)]
    Artifacts[(Local Artifacts<br/>models backtests registry)]
    Providers[OpenAI / Anthropic / Gemini / Ollama]

    User --> UI
    UI --> API
    API --> DB
    API --> Artifacts
    API --> Providers
```

## 2. Backend slice map

```mermaid
flowchart TB
    Main[app/main.py]
    Core[app/core]
    Shared[app/shared]

    Main --> Core
    Main --> Dimensions
    Main --> Analytics
    Main --> Ingest
    Main --> Featuresets
    Main --> Forecasting
    Main --> Backtesting
    Main --> Registry
    Main --> Scenarios
    Main --> RAG
    Main --> Agents
    Main --> Jobs
    Main --> Batch
    Main --> ModelSelection
    Main --> Ops
    Main --> Seeder
    Main --> Demo
    Main --> Config
    Main --> Explainability

    Featuresets --> Shared
    Forecasting --> Shared
    Scenarios --> Shared
    Backtesting --> Shared
```

## 3. Request handling pattern

```mermaid
sequenceDiagram
    participant Browser
    participant Route as FastAPI route
    participant Schema as Pydantic schema
    participant Service as Slice service
    participant DB as AsyncSession

    Browser->>Route: HTTP request
    Route->>Schema: Validate request body/query
    Route->>Service: Call typed service method
    Service->>DB: Read/write data
    DB-->>Service: Rows/state
    Service-->>Route: Response model
    Route-->>Browser: JSON or problem+json
```

## 4. Retail data model

```mermaid
erDiagram
    STORE ||--o{ SALES_DAILY : sells
    PRODUCT ||--o{ SALES_DAILY : sold_as
    CALENDAR ||--o{ SALES_DAILY : dated_by
    STORE ||--o{ PRICE_HISTORY : prices
    PRODUCT ||--o{ PRICE_HISTORY : price_subject
    STORE ||--o{ PROMOTION : promotes
    PRODUCT ||--o{ PROMOTION : promotion_subject
    STORE ||--o{ INVENTORY_SNAPSHOT_DAILY : stocks
    PRODUCT ||--o{ INVENTORY_SNAPSHOT_DAILY : stocked_item
    CALENDAR ||--o{ INVENTORY_SNAPSHOT_DAILY : snapshot_date
```

## 5. Forecast training flow

```mermaid
flowchart LR
    Sales[Sales and retail history]
    Features[Time-safe feature assembly]
    Train[ForecastingService.train_model]
    Model[Trained model bundle]
    Registry[Registry run metadata]

    Sales --> Features
    Features --> Train
    Train --> Model
    Train --> Registry
```

## 6. Prediction and planning flow

```mermaid
flowchart LR
    Run[Registered run or artifact]
    Predict[Predict endpoint]
    Scenario[Scenario simulation]
    Planner[Planner UI]

    Run --> Predict
    Predict --> Planner
    Run --> Scenario
    Scenario --> Planner
```

## 7. Backtesting and champion selection

```mermaid
flowchart TD
    Availability[Pair availability]
    Candidates[Candidate model configs]
    Backtests[Backtest each candidate]
    Rank[Rank by metrics]
    Winner[Winner summary]
    Train[Train selected or winner]
    Promote[Promote alias]

    Availability --> Candidates
    Candidates --> Backtests
    Backtests --> Rank
    Rank --> Winner
    Winner --> Train
    Train --> Promote
```

## 8. Registry and artifact governance

```mermaid
flowchart LR
    Train[Training workflow]
    Artifact[Model artifact on disk]
    Run[(model_run)]
    Alias[(run_alias)]
    Compare[Compare and verify APIs]

    Train --> Artifact
    Train --> Run
    Run --> Alias
    Run --> Compare
    Artifact --> Compare
```

## 9. RAG indexing workflow

```mermaid
flowchart LR
    Source[Markdown / OpenAPI / docs file]
    Hash[Content hash]
    Chunk[Chunker]
    Embed[Embedding provider]
    Store[(rag_source + rag_chunk)]

    Source --> Hash
    Hash --> Chunk
    Chunk --> Embed
    Embed --> Store
```

## 10. RAG retrieval workflow

```mermaid
sequenceDiagram
    participant UI as Knowledge page or agent
    participant API as /rag/retrieve
    participant VDB as pgvector chunks
    participant Provider as Embedding provider

    UI->>API: query text
    API->>Provider: embed query
    Provider-->>API: query vector
    API->>VDB: similarity search
    VDB-->>API: ranked chunks
    API-->>UI: citations and excerpts
```

## 11. Agent chat and approval flow

```mermaid
sequenceDiagram
    participant User
    participant ChatUI as Chat page
    participant WS as /agents/stream
    participant Agent as AgentService
    participant Tools as Agent tools
    participant Approve as /agents/sessions/{id}/approve

    User->>ChatUI: send message
    ChatUI->>WS: session_id + message
    WS->>Agent: invoke agent
    Agent->>Tools: tool call
    alt approval required
        Agent-->>ChatUI: approval_required
        User->>ChatUI: approve or reject
        ChatUI->>Approve: decision
        Approve-->>Agent: continue or stop
    end
    Agent-->>ChatUI: text_delta / complete
```

## 12. Demo pipeline orchestration

```mermaid
flowchart LR
    Start[Showcase or make demo]
    Seed[Seeder]
    Features[Featuresets]
    Train[Train models]
    Backtest[Backtest]
    Register[Register winner]
    Alias[Create alias]
    Knowledge[RAG probe]
    Agent[Agent probe]
    Finish[Summary]

    Start --> Seed
    Seed --> Features
    Features --> Train
    Train --> Backtest
    Backtest --> Register
    Register --> Alias
    Alias --> Knowledge
    Knowledge --> Agent
    Agent --> Finish
```

## 13. Frontend route topology

```mermaid
flowchart TD
    App[frontend/src/App.tsx]
    Dashboard[Dashboard]
    Showcase[Showcase]
    Ops[Ops]
    Explorer[Explorer pages]
    Visualize[Visualize pages]
    Knowledge[Knowledge]
    Chat[Chat]
    Guide[Guide]
    Admin[Admin]

    App --> Dashboard
    App --> Showcase
    App --> Ops
    App --> Explorer
    App --> Visualize
    App --> Knowledge
    App --> Chat
    App --> Guide
    App --> Admin
```

## 14. Frontend data-flow pattern

```mermaid
flowchart LR
    Page[Page]
    Hook[React Query hook]
    Api[api helper]
    Backend[FastAPI endpoint]

    Page --> Hook
    Hook --> Api
    Api --> Backend
```

## 15. Runtime deployment topology

```mermaid
flowchart TB
    subgraph Compose
        Postgres[postgres<br/>pgvector/pg16]
        Backend[backend<br/>uvicorn + FastAPI]
        Frontend[frontend<br/>Vite]
        Ollama[ollama<br/>optional GPU profile]
    end

    Frontend --> Backend
    Backend --> Postgres
    Backend --> Ollama
```

## 16. CI/CD flow

```mermaid
flowchart LR
    Dev[Feature branch]
    PR[PR to dev]
    CI[lint + typecheck + tests + migration check]
    MergeDev[Merge to dev]
    MainPR[PR dev to main]
    ReleasePR[release-please Release PR]
    Tag[Tag and release artifacts]

    Dev --> PR
    PR --> CI
    CI --> MergeDev
    MergeDev --> MainPR
    MainPR --> CI
    CI --> ReleasePR
    ReleasePR --> Tag
```

## 17. Reusable architectural patterns

```mermaid
mindmap
  root((Reusable patterns))
    Vertical slice
      routes
      schemas
      service
      models
      tests
    Shared backend contracts
      settings
      db session
      problem details
      logging
    Frontend workflow pattern
      page
      hook
      component
      lib helper
    AI safety pattern
      schema validated tools
      approval gate
      provider allow-lists
      timeouts and caps
```

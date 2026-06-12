# Deep Dive: AI Engineer

## Scope

This document studies ForecastLabAI through the AI engineer lens: forecasting mechanics, feature safety, model execution, registry semantics, scenario logic, RAG pipeline, agent orchestration, and AI risk controls.

## 1. Research

### AI surface area in the repo

ForecastLabAI has four distinct AI/ML layers:

1. classical forecasting and feature-engineered prediction
2. evaluation and model selection
3. retrieval-augmented generation
4. tool-using agents with approval-gated mutations

That separation is important. This is not one generic "AI layer." It is several different reasoning and execution systems sharing one product.

### Forecasting system

`app/features/forecasting/service.py` is the central forecasting orchestrator. It handles:

- training data loading
- model instantiation
- feature-frame handling
- artifact persistence
- prediction
- feature metadata extraction

The service explicitly documents time-safety and contains version-aware feature-frame logic. That is the right shape for a forecasting platform where leakage is a core product risk.

### Feature safety model

The repo treats time-safety as a first-class invariant:

- lagged features
- shifted rolling windows
- feature-frame contracts in shared code
- leakage tests treated as specification

This is stronger than many ML repos that mention leakage conceptually but do not operationalize it. Here, time-safety is both an implementation rule and a testing rule.

### Model inventory and execution

The forecasting layer supports a mix of:

- naive and seasonal baselines
- moving average variants
- regression-style feature-aware models
- optional heavier models such as LightGBM and XGBoost behind flags

This is a sensible AI-engineering tradeoff:

- cheap baselines for control and comparability
- feature-aware models for richer behavior
- optional advanced learners so the core install stays light

### Backtesting and model selection

The repo goes beyond training into disciplined evaluation:

- time-series CV
- fold metrics
- horizon-bucket metrics
- candidate ranking
- champion workflows
- promotion to aliases

This matters because the AI story is not "we can forecast," but "we can evaluate, compare, and operationalize forecasts."

### Scenario simulation

`app/features/scenarios/service.py` introduces two different planning methods:

1. heuristic post-forecast adjustment
2. `model_exogenous` re-forecasting for feature-aware models

That distinction is product-important and technically honest. The code explicitly labels which path is heuristic and which path is model-driven.

### Registry and artifact lifecycle

Model runs live in registry tables while artifacts live on disk. The registry tracks:

- configs
- metrics
- runtime info
- feature frame version and metadata
- aliasing and compare flows

This is the core reproducibility seam of the ML system. Without it, scenario planning, explainability, and promotion would be much weaker.

### RAG pipeline

`app/features/rag/service.py` shows a standard but careful retrieval pipeline:

- source ingest from content or path
- content hashing for idempotency
- path traversal protection
- chunking by source type
- embedding generation
- pgvector storage
- semantic retrieval with thresholds

The local/provider-switchable design is especially practical for this repo's single-host identity.

### Agent system

`app/features/agents/service.py` orchestrates:

- session lifecycle
- agent selection
- streaming
- tool execution
- approval state
- token and tool-call accounting

The service intentionally forces sequential tool execution because all tools share one DB session and concurrent use would violate SQLAlchemy session constraints. That is a good example of AI engineering being informed by infrastructure reality.

### AI provider control

`app/core/config.py` and the config slice expose runtime control over:

- agent default and fallback model
- embedding provider
- embedding dimensions
- Ollama host/model
- approval requirements
- session limits and timeouts

The ability to switch providers live from the product is one of the stronger AI-platform features in the repo.

## 2. Compose A Role-Based Plan

### AI engineer reading plan

Recommended order:

1. `app/core/config.py`
2. `app/features/featuresets/*`
3. `app/features/forecasting/service.py`
4. `app/features/backtesting/*`
5. `app/features/model_selection/*`
6. `app/features/registry/*`
7. `app/features/scenarios/*`
8. `app/features/rag/service.py`
9. `app/features/agents/service.py`
10. `app/features/agents/tools/*`
11. `frontend/src/pages/knowledge.tsx`
12. `frontend/src/pages/chat.tsx`

### AI systems review plan

Review the repo in these four layers:

1. Predictive ML
   - feature safety
   - train/predict contract
   - artifact compatibility
2. Evaluation and governance
   - backtest output shape
   - candidate ranking
   - alias lifecycle
3. Retrieval
   - ingestion safety
   - chunking strategy
   - embedding/provider constraints
4. Agents
   - tool exposure
   - approval gate correctness
   - session and streaming behavior

### High-value improvement plan

An AI engineer would likely prioritize:

1. clearer model-bundle versioning and compatibility guarantees
2. stronger observability around token use, retrieval quality, and tool outcomes
3. offline evaluation harnesses for retrieval and agent quality
4. explicit latency and cost reporting per provider and workflow
5. tighter provenance reporting across agent answers and scenario-save actions

## 3. Validate

### AI engineering strengths

1. Leakage is treated as a real systems constraint.
2. Model governance is not an afterthought.
3. Scenario simulation is transparent about heuristic versus model-driven logic.
4. RAG indexing is idempotent and includes path safety checks.
5. Agent mutation is approval-gated.
6. Sequential tool execution avoids unsafe session concurrency.

### AI engineering risks

1. Single-host execution couples ML latency to API runtime.
2. Artifact compatibility can become subtle as feature-frame versions evolve.
3. Retrieval quality depends on provider/model settings that can change at runtime.
4. Agent reliability depends on tool schemas, provider behavior, and approval UX all staying aligned.
5. There is limited built-in evaluation telemetry for retrieval and agent quality compared with the maturity of the forecasting layer.

### AI risk controls already present

- strict Pydantic validation at boundaries
- explicit provider allow-lists
- approval-required mutation tools
- request/session limits
- timeout and retry controls
- content-hash idempotency for RAG
- no direct unsafe execution of model output

## 4. Generate

## Generated AI Engineering Findings

### What kind of AI system this is

ForecastLabAI is an applied AI product with two very different forms of intelligence:

1. deterministic statistical/ML forecasting
2. probabilistic LLM-based reasoning and tool use

The repo handles them separately enough to stay sane, while still exposing them inside one product.

### Strongest AI design choices

1. treating time-safety as non-negotiable
2. keeping baseline models in the product
3. preserving registry and artifact provenance
4. making scenario methods explicit
5. showing the RAG corpus directly in the UI
6. forcing human approval for mutating agent actions

### Where the AI system is most mature

The predictive ML and governance story feels the most mature:

- forecasting
- backtesting
- registry
- model selection
- scenario compatibility awareness

The RAG and agent layers are credible and well integrated, but they still have more room for evaluation and observability depth than the classical forecasting side.

### Recommended AI engineering priorities

1. Add retrieval-quality and agent-quality evaluation fixtures.
2. Surface token, provider, retrieval, and tool-call metrics more explicitly.
3. Formalize artifact and feature-frame compatibility in one canonical contract.
4. Keep expanding provenance in agent-visible and user-visible outputs.
5. Protect the distinction between deterministic model workflows and LLM-generated reasoning; that clarity is a strength.

### Final AI engineer view

This is a serious applied AI repository because it does not collapse every intelligence problem into "call an LLM." It uses the right tool for each layer: statistical models for forecasting, retrieval for grounded context, and agents for guided orchestration. The next maturity step is better evaluation and observability around the LLM-powered layers, not more raw capability.

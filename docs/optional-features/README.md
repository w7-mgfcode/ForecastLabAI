# Optional Feature Concepts

This folder contains implementation-oriented product and architecture notes for optional ForecastLabAI features. These are not committed roadmap promises; they are detailed candidate specs that can be promoted into PRPs when selected.

## Feature Documents

| Feature | File | Priority | Complexity |
| --- | --- | --- | --- |
| RAG Corpus Manager | [01-rag-corpus-manager.md](01-rag-corpus-manager.md) | First recommended | Medium |
| ForecastOps Control Center | [02-forecastops-control-center.md](02-forecastops-control-center.md) | Strategic | High |
| Scenario Simulation and What-If Planning | [03-scenario-simulation-what-if-planning.md](03-scenario-simulation-what-if-planning.md) | Strategic | Very High |
| Forecast Explainability and Driver Attribution | [04-forecast-explainability-driver-attribution.md](04-forecast-explainability-driver-attribution.md) | Strategic | High |
| Advanced ML Model Zoo | [05-advanced-ml-model-zoo.md](05-advanced-ml-model-zoo.md) | Strategic | Very High |
| Portfolio Forecasting Batch Runner | [06-portfolio-forecasting-batch-runner.md](06-portfolio-forecasting-batch-runner.md) | Strategic | High |
| Agent Experiment Workbench | [07-agent-experiment-workbench.md](07-agent-experiment-workbench.md) | Strategic | High |
| Demand Anomaly and Data Quality Monitor | [08-demand-anomaly-data-quality-monitor.md](08-demand-anomaly-data-quality-monitor.md) | Medium-term | Medium |
| Model Champion/Challenger Governance | [09-model-champion-challenger-governance.md](09-model-champion-challenger-governance.md) | Medium-term | High |

## Promotion Criteria

Promote one of these documents into a PRP when:

- The user workflow is clear enough to test in the browser.
- The backend contract can be described with typed request/response schemas.
- The implementation can be sliced into independently validatable steps.
- The feature improves the demo narrative without breaking the local-first setup.
- The validation plan includes unit tests, API tests, and browser QA for frontend work.

## Global Documentation

- FastAPI documentation: https://fastapi.tiangolo.com/
- Pydantic documentation: https://docs.pydantic.dev/latest/
- Pydantic AI documentation: https://ai.pydantic.dev/
- SQLAlchemy asyncio documentation: https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html
- React Router documentation: https://reactrouter.com/home
- TanStack Query documentation: https://tanstack.com/query/latest/docs/framework/react/overview
- TanStack Table documentation: https://tanstack.com/table/latest/docs/overview
- shadcn/ui documentation: https://ui.shadcn.com/docs
- Radix UI primitives documentation: https://www.radix-ui.com/primitives/docs
- Tailwind CSS documentation: https://tailwindcss.com/docs
- Recharts documentation: https://recharts.org/en-US/
- scikit-learn documentation: https://scikit-learn.org/stable/
- LightGBM documentation: https://lightgbm.readthedocs.io/
- XGBoost documentation: https://xgboost.readthedocs.io/en/stable/
- Prophet documentation: https://facebook.github.io/prophet/docs/quick_start.html
- SHAP documentation: https://shap.readthedocs.io/en/stable/
- OpenTelemetry Python documentation: https://opentelemetry.io/docs/languages/python/
- OWASP Top 10 for LLM Applications: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework

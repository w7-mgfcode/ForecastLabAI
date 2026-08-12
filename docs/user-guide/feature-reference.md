# Feature Reference

> **Moved.** This reference has been absorbed into the [user manual](../manual/README.md).

> **Note:** the model list in the previous version of this file was out of date — it named seven model types, and the system has **eleven**. The manual is generated against `app/shared/model_taxonomy.py`, the authoritative source.

Its content now lives in:

- **[API reference](../manual/integrator/api-reference.md)** — the shared conventions, the RFC 7807 error envelope, and all twenty endpoint groups.
- **[Forecasting](../manual/analyst/forecasting.md)** — the eleven model types, three families, the V1/V2 feature frame, the eleven feature packs, and how to read feature importance.
- **[Artifacts and the registry](../manual/integrator/artifacts-and-registry.md)** — run lifecycle, artifact verification, and alias semantics.
- **[Champion selector](../manual/analyst/champion-selector.md)** — the `/model-selection/*` workflow.
- **[Data model](../manual/integrator/data-model.md)** — the twenty-three tables and the slices that own them.

The authoritative, always-current API contract remains the generated OpenAPI schema at **http://localhost:8123/docs**.

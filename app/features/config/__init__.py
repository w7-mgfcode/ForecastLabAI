"""Runtime-editable application configuration slice.

Exposes the ``app_config`` key/value override store, the ``/config`` REST
surface, and the service that applies persisted overrides onto the live
``Settings`` singleton (agent LLM model, RAG embedding model, provider keys).
"""

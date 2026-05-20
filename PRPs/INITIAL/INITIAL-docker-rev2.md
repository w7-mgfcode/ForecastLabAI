
---

## FEATURE:

* Implement an end-to-end automated lifecycle management for a multi-container Docker stack.
* **Service Architecture:**
* **Frontend:** React/Vite container.
* **Backend:** Python/FastAPI container.
* **Storage:** PostgreSQL + Qdrant (Vector DB) for RAG support.
* **AI Engine:** Ollama (GPU-enabled via NVIDIA Container Toolkit/CUDA).


* **Automation Goal:** Enable an AI agent to perform "Plan -> Implement -> Validate -> Evaluate" cycles for any new feature request within this specific stack.

## EXAMPLES:

* `examples/docker-compose.yml` - Reference this for network aliases and volume mapping.
* `examples/scripts/healthcheck.sh` - Contains the logic for verifying if PostgreSQL and Qdrant are ready to accept connections before the API starts.
* `examples/tests/smoke_test.py` - Use this as a template to verify that the Backend can successfully ping both the Database and the Ollama endpoint.

## DOCUMENTATION:

* **Docker Documentation:** [https://docs.docker.com/compose/](https://docs.docker.com/compose/)
* **Ollama Docker Guide:** [https://hub.docker.com/r/ollama/ollama](https://hub.docker.com/r/ollama/ollama)
* **Qdrant API Docs:** [https://qdrant.tech/documentation/](https://qdrant.tech/documentation/)
* **Project Internal:** `./docs/architecture.md` (Contains specific networking rules for local GPU passthrough).

## OTHER CONSIDERATIONS:

* **GPU Constraints:** AI agent must check for `nvidia-smi` availability before attempting to modify Ollama configurations.
* **Networking:** All services must use internal Docker networking aliases (e.g., `http://qdrant:6333`, `http://ollama:11434`). Do not use `localhost` for cross-container communication.
* **Validation Logic:** The agent must run a `docker-compose logs` analysis after any change to ensure no "CrashLoopBackOff" is occurring on the GPU-dependent containers.
* **Cleanup:** Every validation pass must conclude with a check that no orphaned containers are left running if the build fails.
* **Persistence:** Ensure `pgdata` and `qdrant_data` are mounted to `./data` to prevent state loss during container restarts.

---

### Implementation Flow Integration

To ensure the agent follows your request, you can pair this `INITIAL.md` with the following instruction:

> "Using the provided `INITIAL.md` context, initiate the **Plan -> Implement -> Validate -> Evaluate** cycle for [INSERT NEW FEATURE]. Begin by reviewing the `docker-compose.yml` and confirming all containers are currently healthy."
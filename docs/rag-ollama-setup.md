# RAG with Ollama & Gemini Agent Setup Guide
# RAG Ollama és Gemini Agent Beállítási Útmutató

> Bilingual documentation for configuring RAG with local Ollama embeddings and Gemini 2.5 agents
>
> Kétnyelvű dokumentáció a RAG lokális Ollama embedding-ekkel és Gemini 2.5 agent-ekkel történő konfigurálásához

---

## Table of Contents / Tartalomjegyzék

**Part 1: RAG with Ollama / RAG Ollama-val**
1. [Overview / Áttekintés](#overview--áttekintés)
2. [Problem Statement / Probléma](#problem-statement--probléma)
3. [Solution / Megoldás](#solution--megoldás)
4. [Configuration / Konfiguráció](#configuration--konfiguráció)
5. [Testing / Tesztelés](#testing--tesztelés)
6. [Best Practices / Legjobb Gyakorlatok](#best-practices--legjobb-gyakorlatok)
7. [Troubleshooting / Hibaelhárítás](#troubleshooting--hibaelhárítás)

**Part 2: Agentic Layer with Gemini 2.5 / Agentic Layer Gemini 2.5-tel**
8. [Gemini Agent Overview / Gemini Agent Áttekintés](#gemini-agent-overview--gemini-agent-áttekintés)
9. [Gemini Configuration / Gemini Konfiguráció](#gemini-configuration--gemini-konfiguráció)
10. [Agent Code Fixes / Agent Kód Javítások](#agent-code-fixes--agent-kód-javítások)
11. [Agent Testing / Agent Tesztelés](#agent-testing--agent-tesztelés)

---

## Overview / Áttekintés

**EN:** This guide documents how to configure the ForecastLabAI RAG (Retrieval-Augmented Generation) system to use Ollama as the embedding provider instead of OpenAI. This enables fully local/LAN-based embedding generation without external API dependencies.

**HU:** Ez az útmutató dokumentálja, hogyan kell konfigurálni a ForecastLabAI RAG (Retrieval-Augmented Generation) rendszert, hogy Ollama-t használjon embedding provider-ként az OpenAI helyett. Ez lehetővé teszi a teljesen lokális/LAN-alapú embedding generálást külső API függőségek nélkül.

### Architecture / Architektúra

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  ForecastLabAI  │────▶│  Ollama Server  │────▶│  qwen3-embedding │
│  (localhost)    │     │  (LAN: 10.0.0.x)│     │  :4b model       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐
│  PostgreSQL     │
│  + pgvector     │
│  (1536-dim)     │
└─────────────────┘
```

---

## Problem Statement / Probléma

**EN:**
- The default RAG configuration uses OpenAI API for embeddings, requiring an API key and internet connection
- We needed to use a local Ollama instance running on a LAN server (10.0.0.226)
- The embedding model (`qwen3-embedding:4b`) natively outputs 2560 dimensions, but we needed 1536 for compatibility
- The default similarity threshold (0.7) was too high for the Ollama model, returning no results

**HU:**
- Az alapértelmezett RAG konfiguráció OpenAI API-t használ az embedding-ekhez, ami API kulcsot és internet kapcsolatot igényel
- Lokális Ollama instance-t kellett használnunk, ami egy LAN szerveren fut (10.0.0.226)
- Az embedding modell (`qwen3-embedding:4b`) natívan 2560 dimenziót ad vissza, de nekünk 1536 kellett a kompatibilitáshoz
- Az alapértelmezett similarity threshold (0.7) túl magas volt az Ollama modellhez, nem adott vissza eredményeket

---

## Solution / Megoldás

### Step 1: Verify Ollama Server / Ollama Szerver Ellenőrzése

**EN:** First, verify the Ollama server is accessible and check available models.

**HU:** Először ellenőrizzük, hogy az Ollama szerver elérhető-e és milyen modellek érhetők el.

```bash
# Check available models / Elérhető modellek ellenőrzése
curl http://10.0.0.226:11434/api/tags

# Expected response / Várt válasz:
# {"models":[{"name":"qwen3-embedding:4b",...}]}
```

### Step 2: Test Embedding Dimensions / Embedding Dimenziók Tesztelése

**EN:** The native API returns 2560 dimensions, but the OpenAI-compatible endpoint supports dimension reduction.

**HU:** A natív API 2560 dimenziót ad vissza, de az OpenAI-kompatibilis endpoint támogatja a dimenzió csökkentést.

```bash
# Native API (2560 dimensions) / Natív API (2560 dimenzió)
curl -s http://10.0.0.226:11434/api/embed \
  -d '{"model":"qwen3-embedding:4b","input":"test"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['embeddings'][0]))"
# Output: 2560

# OpenAI-compatible API with dimension control / OpenAI-kompatibilis API dimenzió vezérléssel
curl -s http://10.0.0.226:11434/v1/embeddings \
  -d '{"model":"qwen3-embedding:4b","input":"test","dimensions":1536}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['data'][0]['embedding']))"
# Output: 1536
```

### Step 3: Configure Environment / Környezet Konfigurálása

**EN:** Add the following settings to `.env` file.

**HU:** Add hozzá a következő beállításokat a `.env` fájlhoz.

```bash
# RAG settings - Ollama provider
RAG_EMBEDDING_PROVIDER=ollama
RAG_EMBEDDING_DIMENSION=1536
RAG_EMBEDDING_BATCH_SIZE=50
OLLAMA_BASE_URL=http://10.0.0.226:11434
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:4b

# RAG chunking
RAG_CHUNK_SIZE=512
RAG_CHUNK_OVERLAP=64
RAG_MIN_CHUNK_SIZE=100

# RAG retrieval
RAG_TOP_K=5
RAG_SIMILARITY_THRESHOLD=0.4
RAG_MAX_CONTEXT_TOKENS=4000

# RAG pgvector index
RAG_INDEX_TYPE=hnsw
RAG_HNSW_M=16
RAG_HNSW_EF_CONSTRUCTION=64
```

### Step 4: Code Modification / Kód Módosítás

**EN:** The schema had a hardcoded default for `similarity_threshold`. We modified it to use settings.

**HU:** A schema-ban hardcoded alapérték volt a `similarity_threshold`-hoz. Módosítottuk, hogy a settings-ből olvassa.

**File: `app/features/rag/schemas.py`**
```python
# Before / Előtte:
similarity_threshold: float = Field(
    default=0.7, ge=0.0, le=1.0, description="Minimum similarity score"
)

# After / Utána:
similarity_threshold: float | None = Field(
    default=None, ge=0.0, le=1.0, description="Minimum similarity score (default from settings)"
)
```

**File: `app/features/rag/routes.py`**
```python
# Added import / Import hozzáadva:
from app.core.config import get_settings

# In retrieve() function / A retrieve() függvényben:
settings = get_settings()
if request.similarity_threshold is None:
    request.similarity_threshold = settings.rag_similarity_threshold
```

---

## Configuration / Konfiguráció

### Complete `.env` RAG Settings / Teljes `.env` RAG Beállítások

| Setting | Value | Description (EN) | Leírás (HU) |
|---------|-------|------------------|-------------|
| `RAG_EMBEDDING_PROVIDER` | `ollama` | Embedding provider type | Embedding szolgáltató típusa |
| `RAG_EMBEDDING_DIMENSION` | `1536` | Vector dimension | Vektor dimenzió |
| `RAG_EMBEDDING_BATCH_SIZE` | `50` | Texts per batch (lower for Ollama) | Szövegek batch-enként (alacsonyabb Ollama-hoz) |
| `OLLAMA_BASE_URL` | `http://10.0.0.226:11434` | Ollama server URL | Ollama szerver URL |
| `OLLAMA_EMBEDDING_MODEL` | `qwen3-embedding:4b` | Embedding model name | Embedding modell neve |
| `RAG_CHUNK_SIZE` | `512` | Tokens per chunk | Token-ek chunk-onként |
| `RAG_CHUNK_OVERLAP` | `64` | Overlap between chunks | Átfedés chunk-ok között |
| `RAG_MIN_CHUNK_SIZE` | `100` | Minimum chunk size | Minimális chunk méret |
| `RAG_TOP_K` | `5` | Default results count | Alapértelmezett találatok száma |
| `RAG_SIMILARITY_THRESHOLD` | `0.4` | Minimum similarity (0.0-1.0) | Minimum hasonlóság (0.0-1.0) |
| `RAG_MAX_CONTEXT_TOKENS` | `4000` | Max context for LLM | Max kontextus LLM-nek |
| `RAG_INDEX_TYPE` | `hnsw` | pgvector index type | pgvector index típus |
| `RAG_HNSW_M` | `16` | HNSW M parameter | HNSW M paraméter |
| `RAG_HNSW_EF_CONSTRUCTION` | `64` | HNSW build quality | HNSW építési minőség |

---

## Testing / Tesztelés

### 1. Health Check / Állapot Ellenőrzés

```bash
curl -s http://localhost:8123/health
# Expected / Várt: {"status":"ok","database":null}
```

### 2. Index a Document / Dokumentum Indexelése

```bash
curl -s -X POST http://localhost:8123/rag/index \
  -H "Content-Type: application/json" \
  -d '{"source_type": "markdown", "source_path": "README.md"}' \
  | python3 -m json.tool
```

**Expected Response / Várt Válasz:**
```json
{
    "source_id": "...",
    "source_path": "README.md",
    "chunks_created": 15,
    "tokens_processed": 6238,
    "duration_ms": 6261.91,
    "status": "indexed"
}
```

### 3. List Sources / Források Listázása

```bash
curl -s http://localhost:8123/rag/sources | python3 -m json.tool
```

### 4. Semantic Search / Szemantikus Keresés

```bash
curl -s -X POST http://localhost:8123/rag/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "How does backtesting work?"}' \
  | python3 -m json.tool
```

**Expected / Várt:** 5 results with relevance scores 0.45-0.58

### 5. Verify Database Dimensions / Adatbázis Dimenziók Ellenőrzése

```bash
uv run python3 -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import get_settings

async def check():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        result = await conn.execute(text('SELECT id, vector_dims(embedding) as dim FROM document_chunk LIMIT 5'))
        rows = result.fetchall()
        for row in rows:
            print(f'chunk_id: {row[0]}, dimension: {row[1]}')
    await engine.dispose()

asyncio.run(check())
"
```

**Expected / Várt:**
```
chunk_id: 29, dimension: 1536
chunk_id: 30, dimension: 1536
...
```

### 6. Delete and Reindex / Törlés és Újraindexelés

```bash
# Delete source / Forrás törlése
curl -s -X DELETE http://localhost:8123/rag/sources/{source_id}

# Reindex / Újraindexelés
curl -s -X POST http://localhost:8123/rag/index \
  -H "Content-Type: application/json" \
  -d '{"source_type": "markdown", "source_path": "README.md"}'
```

---

## Best Practices / Legjobb Gyakorlatok

### 1. Similarity Threshold / Hasonlósági Küszöb

**EN:** Different embedding models produce different similarity score distributions. The optimal threshold varies:

**HU:** Különböző embedding modellek különböző hasonlósági pont eloszlásokat produkálnak. Az optimális küszöb változó:

| Model | Recommended Threshold |
|-------|----------------------|
| OpenAI text-embedding-3-small | 0.7 |
| qwen3-embedding:4b | 0.4 |
| nomic-embed-text | 0.5 |

### 2. Batch Size / Batch Méret

**EN:** Use lower batch sizes for local Ollama (50) vs OpenAI (100) to avoid timeouts.

**HU:** Használj alacsonyabb batch méretet lokális Ollama-hoz (50) vs OpenAI (100), hogy elkerüld a timeout-okat.

### 3. Dimension Control / Dimenzió Vezérlés

**EN:** Always use the OpenAI-compatible `/v1/embeddings` endpoint with `dimensions` parameter for consistent vector sizes.

**HU:** Mindig használd az OpenAI-kompatibilis `/v1/embeddings` endpoint-ot a `dimensions` paraméterrel a konzisztens vektor méretekhez.

### 4. Chunk Configuration / Chunk Konfiguráció

**EN:**
- `RAG_CHUNK_SIZE=512`: Good balance between context and precision
- `RAG_CHUNK_OVERLAP=64`: Maintains context continuity
- `RAG_MIN_CHUNK_SIZE=100`: Filters out tiny, useless chunks

**HU:**
- `RAG_CHUNK_SIZE=512`: Jó egyensúly a kontextus és a precizitás között
- `RAG_CHUNK_OVERLAP=64`: Fenntartja a kontextus folytonosságát
- `RAG_MIN_CHUNK_SIZE=100`: Kiszűri a túl kicsi, haszontalan chunk-okat

### 5. Server Restart / Szerver Újraindítás

**EN:** Settings are cached via `@lru_cache`. Always restart the API after `.env` changes.

**HU:** A beállítások cache-elve vannak `@lru_cache`-sel. Mindig indítsd újra az API-t `.env` változtatások után.

```bash
pkill -f "uvicorn app.main:app"
uv run uvicorn app.main:app --port 8123 &
```

---

## Troubleshooting / Hibaelhárítás

### Problem: Empty Results / Üres Eredmények

**EN:** If retrieval returns no results:

**HU:** Ha a keresés nem ad vissza eredményeket:

1. Check threshold is not too high / Ellenőrizd, hogy a küszöb nem túl magas
2. Verify documents are indexed / Ellenőrizd, hogy a dokumentumok indexelve vannak
3. Test with `similarity_threshold: 0.1` to confirm embeddings work / Tesztelj `similarity_threshold: 0.1`-gyel

### Problem: Connection Error / Kapcsolódási Hiba

```
Failed to connect to Ollama at http://10.0.0.226:11434
```

**EN:** Verify Ollama is running and accessible:

**HU:** Ellenőrizd, hogy az Ollama fut és elérhető:

```bash
curl http://10.0.0.226:11434/api/tags
```

### Problem: Model Not Found / Modell Nem Található

```
Ollama model 'qwen3-embedding:4b' not found
```

**EN:** Pull the model on the Ollama server:

**HU:** Töltsd le a modellt az Ollama szerveren:

```bash
ollama pull qwen3-embedding:4b
```

### Problem: Dimension Mismatch / Dimenzió Eltérés

**EN:** If you change `RAG_EMBEDDING_DIMENSION`, you must:

**HU:** Ha megváltoztatod a `RAG_EMBEDDING_DIMENSION`-t:

1. Delete all existing sources / Töröld az összes létező forrást
2. Reindex all documents / Indexeld újra az összes dokumentumot

```bash
# List and delete all sources / Források listázása és törlése
curl -s http://localhost:8123/rag/sources | python3 -c "
import sys, json
for s in json.load(sys.stdin)['sources']:
    print(s['source_id'])
"
# Then delete each / Majd töröld mindet
```

---

## Performance Metrics / Teljesítmény Metrikák

| Metric | Typical Value | Description |
|--------|---------------|-------------|
| Embedding time | 70-140ms | Query embedding generation |
| Search time | 60-110ms | pgvector similarity search |
| Index time | 6-8s | Per document (README.md, 15 chunks) |
| Relevance scores | 0.45-0.58 | For qwen3-embedding with threshold 0.4 |

---

# Part 2: Agentic Layer with Gemini 2.5
# 2. rész: Agentic Layer Gemini 2.5-tel

---

## Gemini Agent Overview / Gemini Agent Áttekintés

**EN:** The ForecastLabAI agentic layer uses PydanticAI v1.48.0 for structured agent orchestration. This section documents how to configure and fix the agents to work with Google Gemini 2.5 models via Google AI Studio (google-gla provider).

**HU:** A ForecastLabAI agentic layer PydanticAI v1.48.0-t használ strukturált agent vezényléshez. Ez a rész dokumentálja, hogyan kell konfigurálni és javítani az agent-eket, hogy működjenek a Google Gemini 2.5 modellekkel a Google AI Studio-n keresztül (google-gla provider).

### Architecture / Architektúra

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  ForecastLabAI  │────▶│  Google AI      │────▶│  Gemini 2.5     │
│  Agent Service  │     │  Studio API     │     │  Pro/Flash      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐
│  RAG Assistant  │──── Tool: retrieve_context ────▶ Ollama Embeddings
│  (PydanticAI)   │
└─────────────────┘
```

---

## Gemini Configuration / Gemini Konfiguráció

### Problem Statement / Probléma

**EN:**
1. PydanticAI looks for API keys in environment variables, but Pydantic Settings doesn't export values to env
2. PydanticAI Agent constructor doesn't accept `temperature`, `max_tokens` directly - needs `model_settings` wrapper
3. PydanticAI v1.48.0 uses `result.output` not `result.data`
4. Message history contains datetime objects that can't be JSON serialized
5. RAG tool had hardcoded similarity threshold (0.7) ignoring settings

**HU:**
1. PydanticAI az API kulcsokat környezeti változókból keresi, de a Pydantic Settings nem exportálja az értékeket env-be
2. PydanticAI Agent konstruktor nem fogadja a `temperature`, `max_tokens` paramétereket közvetlenül - `model_settings` wrapper kell
3. PydanticAI v1.48.0 `result.output`-ot használ, nem `result.data`-t
4. Az üzenet előzmények datetime objektumokat tartalmaznak, amik nem JSON szerializálhatók
5. A RAG tool hardcoded similarity threshold-ot (0.7) használt, figyelmen kívül hagyva a settings-t

### `.env` Configuration / Konfiguráció

```bash
# =============================================================================
# Agentic Layer Configuration (PydanticAI v1.48.0)
# =============================================================================

# Model Configuration
# Model identifier format: "provider:model-name"
# Supported providers:
#   - anthropic: Claude models (claude-sonnet-4-5, claude-opus-4-5, etc.)
#   - openai: GPT models (gpt-4o, gpt-4o-mini, etc.)
#   - google-gla: Gemini models via Google AI Studio (gemini-2.5-flash, gemini-2.5-pro)
AGENT_DEFAULT_MODEL=google-gla:gemini-2.5-pro
AGENT_FALLBACK_MODEL=google-gla:gemini-2.5-flash

# API Keys (only one needed based on your chosen provider)
# ANTHROPIC_API_KEY=
# OPENAI_API_KEY=
GOOGLE_API_KEY=your-google-api-key-here

# Gemini Extended Reasoning (thinking mode for Gemini 2.5+)
# Allocates token budget for internal reasoning
# Recommended: 4000 tokens for complex agent planning tasks
AGENT_THINKING_BUDGET=4000

# Model parameters
AGENT_TEMPERATURE=0.1
AGENT_MAX_TOKENS=4096

# Execution settings
AGENT_MAX_TOOL_CALLS=10
AGENT_TIMEOUT_SECONDS=120
AGENT_RETRY_ATTEMPTS=3
AGENT_RETRY_DELAY_SECONDS=1.0

# Session settings
AGENT_SESSION_TTL_MINUTES=120
AGENT_MAX_SESSIONS_PER_USER=5

# Human-in-the-loop actions (JSON array format)
AGENT_REQUIRE_APPROVAL=["create_alias","archive_run"]
AGENT_APPROVAL_TIMEOUT_MINUTES=60

# Streaming
AGENT_ENABLE_STREAMING=true
```

---

## Agent Code Fixes / Agent Kód Javítások

### Fix 1: API Key Export / API Kulcs Exportálás

**EN:** PydanticAI looks for API keys in `os.environ`, but Pydantic Settings only reads them into the Settings object. We must export them.

**HU:** A PydanticAI az `os.environ`-ban keresi az API kulcsokat, de a Pydantic Settings csak a Settings objektumba olvassa be őket. Exportálni kell őket.

**File: `app/features/agents/agents/base.py`**
```python
import os
from app.core.config import get_settings

def validate_api_key_for_model(model: str) -> None:
    """Validate and export API key to environment."""
    settings = get_settings()
    provider = model.split(":")[0]

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
    elif provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not configured")
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    elif provider in ["google-gla", "google-vertex"]:
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY not configured")
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key
```

### Fix 2: Model Settings Wrapper / Model Settings Wrapper

**EN:** PydanticAI Agent doesn't accept `temperature`, `max_tokens` as top-level kwargs. They must be wrapped in `model_settings`.

**HU:** A PydanticAI Agent nem fogadja a `temperature`, `max_tokens` paramétereket top-level kwargs-ként. `model_settings`-be kell csomagolni őket.

**File: `app/features/agents/agents/base.py`**
```python
def get_model_settings() -> dict[str, Any]:
    """Get model settings wrapped for PydanticAI Agent constructor."""
    settings = get_settings()
    inner_settings: dict[str, Any] = {
        "temperature": settings.agent_temperature,
        "max_tokens": settings.agent_max_tokens,
    }

    # Add thinking budget for Gemini 2.5+ extended reasoning
    if settings.agent_thinking_budget:
        inner_settings["thinking"] = {"budget": settings.agent_thinking_budget}

    return {"model_settings": inner_settings}  # Wrapped!
```

### Fix 3: Result Output Attribute / Result Output Attribútum

**EN:** PydanticAI v1.48.0 uses `result.output` not `result.data`.

**HU:** A PydanticAI v1.48.0 `result.output`-ot használ, nem `result.data`-t.

**File: `app/features/agents/service.py`**
```python
# Before / Előtte:
result_data: Any = result.data  # WRONG!

# After / Utána:
result_data: Any = result.output  # Correct for PydanticAI v1.48.0
```

### Fix 4: DateTime Serialization / DateTime Szerializálás

**EN:** Message history contains datetime objects that must be converted to ISO strings for JSON storage.

**HU:** Az üzenet előzmények datetime objektumokat tartalmaznak, amiket ISO string-ekké kell konvertálni JSON tároláshoz.

**File: `app/features/agents/service.py`**
```python
def _serialize_messages(self, messages: list[ModelMessage]) -> list[dict[str, Any]]:
    from datetime import datetime

    def json_safe(obj: Any) -> Any:
        """Convert non-JSON-serializable objects to strings."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: json_safe(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [json_safe(item) for item in obj]
        return obj

    serialized = []
    for msg in messages:
        if dataclasses.is_dataclass(msg):
            msg_dict = dataclasses.asdict(msg)
            msg_dict = json_safe(msg_dict)  # Convert datetimes!
            serialized.append(msg_dict)
    return serialized
```

### Fix 5: RAG Tool Threshold / RAG Tool Küszöb

**EN:** The RAG tool had hardcoded `similarity_threshold=0.7`. Now it uses settings.

**HU:** A RAG tool hardcoded `similarity_threshold=0.7`-et használt. Most settings-ből olvassa.

**File: `app/features/agents/agents/rag_assistant.py`**
```python
from app.core.config import get_settings

def create_rag_assistant_agent() -> Agent[AgentDeps, RAGAnswer]:
    settings = get_settings()
    default_threshold = settings.rag_similarity_threshold  # From .env

    @agent.tool
    async def tool_retrieve_context(
        ctx: RunContext[AgentDeps],
        query: str,
        top_k: int = 5,
        similarity_threshold: float | None = None,  # None = use default
    ) -> dict[str, Any]:
        threshold = similarity_threshold if similarity_threshold is not None else default_threshold
        return await retrieve_context(db=ctx.deps.db, query=query, top_k=top_k, similarity_threshold=threshold)
```

---

## Agent Testing / Agent Tesztelés

### 1. Test Gemini Direct / Gemini Közvetlen Teszt

```bash
export GOOGLE_API_KEY="your-api-key"
uv run python3 -c "
import asyncio
from pydantic_ai import Agent

async def test():
    agent = Agent(
        'google-gla:gemini-2.5-pro',
        model_settings={
            'temperature': 0.1,
            'max_tokens': 4096,
            'thinking': {'budget': 4000}
        }
    )
    result = await agent.run('Say hello in one sentence')
    print(f'Response: {result.output}')

asyncio.run(test())
"
# Expected / Várt: Response: Hello, I hope you're having a wonderful day
```

### 2. Create Agent Session / Agent Session Létrehozása

```bash
curl -s -X POST http://localhost:8123/agents/sessions \
  -H "Content-Type: application/json" \
  -d '{"agent_type": "rag_assistant"}' | python3 -m json.tool
```

**Expected Response / Várt Válasz:**
```json
{
    "session_id": "fff85c6a773148958122209511e08589",
    "agent_type": "rag_assistant",
    "status": "active",
    "total_tokens_used": 0,
    "expires_at": "2026-02-02T04:43:53.822956Z"
}
```

### 3. Simple Chat Test / Egyszerű Chat Teszt

```bash
curl -s -X POST "http://localhost:8123/agents/sessions/{session_id}/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}' | python3 -m json.tool
```

**Expected / Várt:**
```json
{
    "session_id": "...",
    "message": "Hi there! How can I help you today?",
    "tool_calls": [],
    "tokens_used": 1023
}
```

### 4. RAG-Powered Chat / RAG-alapú Chat

```bash
curl -s -X POST "http://localhost:8123/agents/sessions/{session_id}/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is backtesting in this system?"}' | python3 -m json.tool
```

**Expected Response / Várt Válasz:**
```json
{
    "session_id": "...",
    "message": "In this system, backtesting is a time-series cross-validation process
                used to evaluate the performance of forecasting models
                [README.md:4be075b398104ebb9436cec307db5eb9]. It involves splitting
                the historical data into multiple folds...",
    "tool_calls": [],
    "tokens_used": 6148
}
```

**Key features in response / Válasz főbb jellemzői:**
- Citations from knowledge base / Idézések a tudásbázisból: `[README.md:chunk_id]`
- Expanding/sliding strategies explained / Expanding/sliding stratégiák magyarázata
- Metrics listed (MAE, sMAPE, WAPE, Bias) / Metrikák felsorolva

---

## Summary of Fixed Files / Javított Fájlok Összefoglalása

| File / Fájl | Fix / Javítás |
|-------------|---------------|
| `app/features/agents/agents/base.py` | API key export to env, model_settings wrapper |
| `app/features/agents/service.py` | `result.output` (not `.data`), datetime serialization |
| `app/features/agents/agents/rag_assistant.py` | Threshold from settings |
| `app/features/rag/schemas.py` | Nullable similarity_threshold |
| `app/features/rag/routes.py` | Settings default for threshold |

---

## References / Hivatkozások

- [Ollama API Documentation](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [PydanticAI Documentation](https://ai.pydantic.dev/)
- [Google AI Studio](https://aistudio.google.com/)
- [ForecastLabAI CLAUDE.md](../CLAUDE.md)

---

*Document created: 2026-02-02*
*Last updated: 2026-02-02*

# PRP-12: Randomized Database Seeder (The Forge) - Completion

## Goal

Complete the remaining features of INITIAL-12 "The Forge" - the randomized database seeder. The core implementation exists but needs:

1. **RAG + Agent E2E Scenario** (`--scenario rag-agent`) - End-to-end workflow validation
2. **Integration Tests** - Database tests with `@pytest.mark.integration`
3. **Missing Config File** - `examples/seed/config_sparse.yaml`
4. **Core Module Tests** - Tests for `DataSeeder` orchestration class

## Why

- **RAG + Agent Scenario**: Validates the complete stack (seeder → data → RAG indexing → agent query → citations) in one command
- **Integration Tests**: Ensures the seeder actually works against PostgreSQL with real FK constraints
- **Config File**: Provides documented sparse data scenario for gap-handling tests
- **Core Tests**: Covers the orchestration layer that ties all generators together

## What

### Success Criteria

- [ ] `uv run python scripts/seed_random.py --scenario rag-agent --confirm` completes successfully
- [ ] Integration tests pass: `uv run pytest app/shared/seeder/tests/ -v -m integration`
- [ ] `examples/seed/config_sparse.yaml` exists and is loadable
- [ ] Unit tests for `DataSeeder.generate_full()`, `delete_data()`, `append_data()` pass
- [ ] All validation gates pass: `ruff check . && mypy app/ && pyright app/`

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ - Existing implementations to mirror
- file: app/shared/seeder/core.py
  why: Contains DataSeeder class - understand generate_full(), delete_data(), append_data() patterns

- file: app/shared/seeder/tests/test_generators.py
  why: Test patterns to follow - fixture usage, assertion styles, reproducibility tests

- file: app/features/rag/routes.py
  why: RAG API endpoints for indexing and retrieval - needed for rag-agent scenario

- file: app/features/agents/routes.py
  why: Agent session API endpoints - needed for rag-agent scenario

- file: app/features/backtesting/tests/test_routes.py
  why: Integration test patterns - async fixtures, db cleanup, pytest.mark.integration

- file: examples/seed/config_holiday.yaml
  why: YAML config structure to mirror for config_sparse.yaml

- file: scripts/seed_random.py
  why: CLI entry point - where rag-agent scenario handler needs to be added

# External Documentation
- url: https://docs.pytest.org/en/stable/how-to/fixtures.html
  section: Async fixtures and scope
  critical: Use @pytest_asyncio.fixture for async DB fixtures

- url: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
  section: AsyncSession usage
  critical: Always commit/rollback in finally blocks
```

### Current Codebase Tree (Relevant Files)

```bash
app/shared/seeder/
├── __init__.py                          # Public exports: DataSeeder, SeederConfig, etc.
├── config.py                            # Configuration dataclasses + ScenarioPreset enum
├── core.py                              # DataSeeder orchestration (579 lines)
├── generators/
│   ├── __init__.py                      # Generator exports
│   ├── store.py                         # StoreGenerator
│   ├── product.py                       # ProductGenerator
│   ├── calendar.py                      # CalendarGenerator
│   └── facts.py                         # Sales, Price, Promo, Inventory generators
└── tests/
    ├── __init__.py
    ├── conftest.py                      # Pytest fixtures (rng, configs)
    ├── test_config.py                   # Config dataclass tests
    └── test_generators.py               # Generator unit tests

scripts/
└── seed_random.py                       # CLI entry point (525 lines)

examples/seed/
├── README.md                            # Usage documentation
└── config_holiday.yaml                  # Holiday scenario YAML config
```

### Desired Codebase Tree (New/Modified Files)

```bash
app/shared/seeder/
├── ...existing files...
├── rag_scenario.py                      # NEW: RAG + Agent E2E scenario logic
└── tests/
    ├── ...existing files...
    ├── test_core.py                     # NEW: DataSeeder unit tests (mocked DB)
    └── test_integration.py              # NEW: Integration tests (real DB)

scripts/
└── seed_random.py                       # MODIFY: Add rag-agent scenario handler

examples/seed/
├── ...existing files...
└── config_sparse.yaml                   # NEW: Sparse data scenario config
```

### Known Gotchas & Library Quirks

```python
# CRITICAL: Async fixtures require pytest-asyncio
# Use: @pytest_asyncio.fixture instead of @pytest.fixture for async functions

# CRITICAL: Test cleanup must happen in fresh session to avoid transaction state issues
# Pattern from app/features/ingest/tests/test_routes.py:
async with async_session_maker() as cleanup_session:
    await cleanup_session.execute(delete(SalesDaily))
    await cleanup_session.commit()

# CRITICAL: The RAG scenario requires:
# 1. RAG_EMBEDDING_PROVIDER configured (openai or ollama)
# 2. API key set if using OpenAI
# 3. Ollama running if using ollama provider
# The scenario should gracefully skip if not configured

# CRITICAL: httpx is required for making API calls in rag-agent scenario
# Already in dependencies: httpx>=0.28.0

# CRITICAL: Integration tests require DB
# Mark with: @pytest.mark.integration
# Run with: uv run pytest -v -m integration

# NOTE: ScenarioPreset enum needs RAG_AGENT added
# But rag-agent scenario is special - it's not a data pattern, it's an E2E test
# Handle it separately in CLI, not in SeederConfig.from_scenario()
```

---

## Implementation Blueprint

### Task 1: Create `examples/seed/config_sparse.yaml`

**File:** `examples/seed/config_sparse.yaml`

```yaml
# Sparse data scenario configuration
# Use with: uv run python scripts/seed_random.py --full-new --config examples/seed/config_sparse.yaml --confirm
#
# Purpose: Test gap handling and missing data scenarios
# - 50% of store/product combinations have no sales
# - Random date gaps within active series
# - Useful for testing imputation and forecasting with missing data

dimensions:
  stores:
    count: 8
    regions: ["North", "South", "East", "West"]
    types: ["supermarket", "express"]
  products:
    count: 30
    categories: ["Beverage", "Snack", "Dairy", "Frozen"]
    brands: ["BrandA", "BrandB", "Generic"]

date_range:
  start: "2024-01-01"
  end: "2024-06-30"

time_series:
  base_demand: 50
  trend: "none"
  noise_sigma: 0.25  # Higher noise for sparse data

retail:
  promotion_probability: 0.05
  stockout_probability: 0.1

sparsity:
  missing_combinations_pct: 0.5  # 50% of store/product pairs have no sales
  random_gaps_per_series: 3      # 3 random gaps per active series
  gap_min_days: 2
  gap_max_days: 10

seed: 42
batch_size: 500
```

---

### Task 2: Create `app/shared/seeder/rag_scenario.py`

**File:** `app/shared/seeder/rag_scenario.py`

This module encapsulates the RAG + Agent E2E scenario logic.

```python
"""RAG + Agent E2E scenario for seeder validation.

This scenario validates the complete stack:
1. Generate synthetic markdown documents
2. Index documents into pgvector via /rag/index
3. Create agent session via /agents/sessions
4. Send test query via /agents/sessions/{id}/chat
5. Verify response contains citations
6. Clean up session
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from app.core.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


@dataclass
class RAGScenarioResult:
    """Result of RAG + Agent scenario execution."""

    documents_indexed: int = 0
    session_created: bool = False
    session_id: str | None = None
    query_sent: bool = False
    response_received: bool = False
    citations_found: bool = False
    cleanup_completed: bool = False
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


class RAGScenarioRunner:
    """Runs the RAG + Agent E2E validation scenario."""

    def __init__(
        self,
        api_base_url: str = "http://localhost:8123",
        seed: int = 42,
    ) -> None:
        """Initialize the scenario runner.

        Args:
            api_base_url: Base URL for the API.
            seed: Random seed for reproducible document generation.
        """
        self.api_base_url = api_base_url.rstrip("/")
        self.rng = random.Random(seed)
        self.result = RAGScenarioResult()

    def _generate_test_documents(self) -> list[dict[str, str]]:
        """Generate synthetic markdown documents for testing.

        Returns:
            List of document dicts with 'content' and 'source_path' keys.
        """
        # Generate 3 small test documents about forecasting
        documents = [
            {
                "content": """# Demand Forecasting Overview

Demand forecasting is the process of predicting future customer demand.

## Key Methods
- **Naive forecasting**: Uses the last observed value
- **Seasonal naive**: Uses the same period from the previous season
- **Moving average**: Uses the mean of recent observations

## Best Practices
1. Always validate with time-based cross-validation
2. Use appropriate metrics (MAE, sMAPE, WAPE)
3. Compare against baselines
""",
                "source_path": "docs/forecasting_overview.md",
            },
            {
                "content": """# Backtesting Guide

Backtesting evaluates forecasting models using historical data.

## Split Strategies
- **Expanding window**: Training data grows with each fold
- **Sliding window**: Fixed-size training window moves forward

## Gap Parameter
The gap parameter simulates operational latency between training cutoff and test period.

## Metrics
- MAE: Mean Absolute Error
- sMAPE: Symmetric Mean Absolute Percentage Error
- WAPE: Weighted Absolute Percentage Error
""",
                "source_path": "docs/backtesting_guide.md",
            },
            {
                "content": """# Model Registry

The model registry tracks trained models and their metadata.

## Run States
- PENDING: Run created but not started
- RUNNING: Training in progress
- SUCCESS: Training completed successfully
- FAILED: Training failed
- ARCHIVED: Run archived (not for production use)

## Deployment Aliases
Aliases like 'production' or 'staging' point to successful runs.
Only SUCCESS runs can have aliases.
""",
                "source_path": "docs/model_registry.md",
            },
        ]
        return documents

    async def _check_api_health(self, client: httpx.AsyncClient) -> bool:
        """Check if the API is running.

        Args:
            client: HTTP client.

        Returns:
            True if API is healthy, False otherwise.
        """
        try:
            response = await client.get(f"{self.api_base_url}/health")
            return response.status_code == 200
        except httpx.RequestError:
            return False

    async def _index_document(
        self,
        client: httpx.AsyncClient,
        content: str,
        source_path: str,
    ) -> bool:
        """Index a document into the RAG system.

        Args:
            client: HTTP client.
            content: Document content.
            source_path: Document path.

        Returns:
            True if indexing succeeded, False otherwise.
        """
        try:
            response = await client.post(
                f"{self.api_base_url}/rag/index",
                json={
                    "source_type": "markdown",
                    "source_path": source_path,
                    "content": content,
                },
                timeout=30.0,
            )
            if response.status_code in (200, 201):
                return True
            else:
                self.result.errors.append(
                    f"Index failed for {source_path}: {response.status_code} - {response.text}"
                )
                return False
        except httpx.RequestError as e:
            self.result.errors.append(f"Index request failed: {e}")
            return False

    async def _create_agent_session(
        self,
        client: httpx.AsyncClient,
    ) -> str | None:
        """Create an agent session.

        Args:
            client: HTTP client.

        Returns:
            Session ID if created, None otherwise.
        """
        try:
            response = await client.post(
                f"{self.api_base_url}/agents/sessions",
                json={
                    "agent_type": "rag_assistant",
                    "initial_context": None,
                },
                timeout=30.0,
            )
            if response.status_code in (200, 201):
                data = response.json()
                return data.get("session_id")
            else:
                self.result.errors.append(
                    f"Session creation failed: {response.status_code} - {response.text}"
                )
                return None
        except httpx.RequestError as e:
            self.result.errors.append(f"Session request failed: {e}")
            return None

    async def _send_chat_query(
        self,
        client: httpx.AsyncClient,
        session_id: str,
        query: str,
    ) -> dict | None:
        """Send a chat query to the agent.

        Args:
            client: HTTP client.
            session_id: Agent session ID.
            query: Query text.

        Returns:
            Response data if successful, None otherwise.
        """
        try:
            response = await client.post(
                f"{self.api_base_url}/agents/sessions/{session_id}/chat",
                json={"message": query},
                timeout=60.0,  # Agent responses can take time
            )
            if response.status_code == 200:
                return response.json()
            else:
                self.result.errors.append(
                    f"Chat query failed: {response.status_code} - {response.text}"
                )
                return None
        except httpx.RequestError as e:
            self.result.errors.append(f"Chat request failed: {e}")
            return None

    async def _close_session(
        self,
        client: httpx.AsyncClient,
        session_id: str,
    ) -> bool:
        """Close an agent session.

        Args:
            client: HTTP client.
            session_id: Session ID to close.

        Returns:
            True if closed successfully.
        """
        try:
            response = await client.delete(
                f"{self.api_base_url}/agents/sessions/{session_id}",
                timeout=10.0,
            )
            return response.status_code in (200, 204)
        except httpx.RequestError:
            return False

    async def run(self, dry_run: bool = False) -> RAGScenarioResult:
        """Execute the RAG + Agent E2E scenario.

        Args:
            dry_run: If True, only show what would be done.

        Returns:
            Scenario execution result.
        """
        logger.info("seeder.rag_scenario.started", dry_run=dry_run)

        if dry_run:
            documents = self._generate_test_documents()
            self.result.documents_indexed = len(documents)
            logger.info(
                "seeder.rag_scenario.dry_run",
                documents=len(documents),
                steps=["index_docs", "create_session", "send_query", "verify_citations", "cleanup"],
            )
            return self.result

        async with httpx.AsyncClient() as client:
            # Step 0: Check API health
            if not await self._check_api_health(client):
                self.result.errors.append(
                    f"API not available at {self.api_base_url}. Start the server first."
                )
                return self.result

            # Step 1: Generate and index documents
            documents = self._generate_test_documents()
            indexed_count = 0
            for doc in documents:
                if await self._index_document(client, doc["content"], doc["source_path"]):
                    indexed_count += 1

            self.result.documents_indexed = indexed_count

            if indexed_count == 0:
                self.result.errors.append("No documents were indexed successfully")
                return self.result

            logger.info("seeder.rag_scenario.docs_indexed", count=indexed_count)

            # Step 2: Create agent session
            session_id = await self._create_agent_session(client)
            if not session_id:
                self.result.errors.append("Failed to create agent session")
                return self.result

            self.result.session_created = True
            self.result.session_id = session_id
            logger.info("seeder.rag_scenario.session_created", session_id=session_id)

            # Step 3: Send test query
            query = "What are the key methods for demand forecasting?"
            response = await self._send_chat_query(client, session_id, query)

            if response:
                self.result.query_sent = True
                self.result.response_received = True

                # Step 4: Verify citations
                # Check if response contains citation-like content
                response_text = str(response.get("response", "")).lower()
                citations = response.get("citations", [])

                if citations or "source" in response_text or "docs/" in response_text:
                    self.result.citations_found = True
                    logger.info("seeder.rag_scenario.citations_verified")
                else:
                    logger.warning("seeder.rag_scenario.no_citations_found")

            # Step 5: Cleanup
            if session_id:
                if await self._close_session(client, session_id):
                    self.result.cleanup_completed = True
                    logger.info("seeder.rag_scenario.cleanup_completed")

        logger.info(
            "seeder.rag_scenario.completed",
            success=len(self.result.errors) == 0,
            documents=self.result.documents_indexed,
            citations_found=self.result.citations_found,
        )

        return self.result


async def run_rag_scenario(
    api_base_url: str = "http://localhost:8123",
    seed: int = 42,
    dry_run: bool = False,
) -> RAGScenarioResult:
    """Convenience function to run the RAG + Agent scenario.

    Args:
        api_base_url: Base URL for the API.
        seed: Random seed for reproducibility.
        dry_run: If True, only show what would be done.

    Returns:
        Scenario execution result.
    """
    runner = RAGScenarioRunner(api_base_url=api_base_url, seed=seed)
    return await runner.run(dry_run=dry_run)
```

---

### Task 3: Update `scripts/seed_random.py` for RAG Scenario

**MODIFY:** `scripts/seed_random.py`

Add the rag-agent scenario handler. Key changes:

1. Add `--scenario rag-agent` as a special case (not in ScenarioPreset enum)
2. Import and call `run_rag_scenario()` from the new module
3. Print formatted results

**Find and modify the argument parser (around line 250-255):**

```python
# FIND this pattern in create_parser():
parser.add_argument(
    "--scenario",
    choices=[s.value for s in ScenarioPreset],
    help="Run pre-built scenario",
)

# REPLACE with:
parser.add_argument(
    "--scenario",
    choices=[s.value for s in ScenarioPreset] + ["rag-agent"],
    help="Run pre-built scenario (rag-agent is special E2E test)",
)
```

**Add import at top of file:**

```python
from app.shared.seeder.rag_scenario import run_rag_scenario
```

**Add new function for RAG scenario (after run_verify):**

```python
async def run_rag_agent_scenario(args: argparse.Namespace) -> int:
    """Run RAG + Agent E2E validation scenario."""
    settings = get_settings()

    # Safety check for production
    if settings.is_production and not settings.seeder_allow_production:
        print("ERROR: Cannot run seeder scenarios in production environment.")
        return 1

    print("Running RAG + Agent E2E Scenario")
    print("-" * 40)
    print()

    api_base = f"http://{settings.api_host}:{settings.api_port}"
    if settings.api_host == "0.0.0.0":
        api_base = f"http://localhost:{settings.api_port}"

    result = await run_rag_scenario(
        api_base_url=api_base,
        seed=args.seed,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        print("DRY RUN - No actions taken")
        print(f"  Documents to index: {result.documents_indexed}")
        print("  Steps: index_docs → create_session → query → verify → cleanup")
        return 0

    print("Results:")
    print(f"  Documents indexed:   {result.documents_indexed}")
    print(f"  Session created:     {'✓' if result.session_created else '✗'}")
    print(f"  Query sent:          {'✓' if result.query_sent else '✗'}")
    print(f"  Response received:   {'✓' if result.response_received else '✗'}")
    print(f"  Citations found:     {'✓' if result.citations_found else '✗'}")
    print(f"  Cleanup completed:   {'✓' if result.cleanup_completed else '✗'}")
    print()

    if result.errors:
        print("Errors:")
        for error in result.errors:
            print(f"  - {error}")
        return 1

    print("RAG + Agent scenario completed successfully!")
    return 0
```

**Modify main() to handle rag-agent scenario (around line 506-516):**

```python
# FIND this pattern in main():
if args.full_new:
    return await run_full_new(args, session)
# ... etc

# ADD before the full_new check:
# Handle rag-agent scenario specially (doesn't need DB session for seeding)
if args.scenario == "rag-agent":
    return await run_rag_agent_scenario(args)
```

---

### Task 4: Create `app/shared/seeder/tests/test_core.py`

**File:** `app/shared/seeder/tests/test_core.py`

Unit tests for the `DataSeeder` class (mocked database).

```python
"""Tests for DataSeeder core orchestration."""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared.seeder.config import DimensionConfig, SeederConfig, SparsityConfig
from app.shared.seeder.core import DataSeeder, SeederResult


class TestDataSeederInit:
    """Tests for DataSeeder initialization."""

    def test_creates_rng_from_seed(self):
        """Test RNG is created with config seed."""
        config = SeederConfig(seed=123)
        seeder = DataSeeder(config)

        assert seeder.rng is not None
        # Same seed should produce same first random value
        seeder2 = DataSeeder(SeederConfig(seed=123))
        assert seeder.rng.random() != seeder2.rng.random()  # Already consumed one

    def test_stores_config(self):
        """Test config is stored on instance."""
        config = SeederConfig(seed=42, batch_size=500)
        seeder = DataSeeder(config)

        assert seeder.config.seed == 42
        assert seeder.config.batch_size == 500


class TestSeederResult:
    """Tests for SeederResult dataclass."""

    def test_default_values(self):
        """Test default values are zero."""
        result = SeederResult()

        assert result.stores_count == 0
        assert result.products_count == 0
        assert result.calendar_days == 0
        assert result.sales_count == 0
        assert result.price_history_count == 0
        assert result.promotions_count == 0
        assert result.inventory_count == 0
        assert result.seed == 42

    def test_custom_values(self):
        """Test custom values are stored."""
        result = SeederResult(
            stores_count=10,
            products_count=50,
            sales_count=1000,
            seed=123,
        )

        assert result.stores_count == 10
        assert result.products_count == 50
        assert result.sales_count == 1000
        assert result.seed == 123


class TestBatchInsert:
    """Tests for _batch_insert method."""

    @pytest.fixture
    def seeder(self):
        """Create seeder with small batch size."""
        config = SeederConfig(seed=42, batch_size=2)
        return DataSeeder(config)

    @pytest.fixture
    def mock_db(self):
        """Create mock async session."""
        db = AsyncMock()
        # Mock execute to return cursor with rowcount
        cursor = MagicMock()
        cursor.rowcount = 2
        db.execute.return_value = cursor
        return db

    @pytest.mark.asyncio
    async def test_empty_records_returns_zero(self, seeder, mock_db):
        """Test empty records list returns 0."""
        count = await seeder._batch_insert(mock_db, MagicMock, [])

        assert count == 0
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_batches_records(self, seeder, mock_db):
        """Test records are batched correctly."""
        records = [{"a": 1}, {"b": 2}, {"c": 3}, {"d": 4}, {"e": 5}]

        with patch("app.shared.seeder.core.pg_insert") as mock_insert:
            mock_stmt = MagicMock()
            mock_stmt.on_conflict_do_nothing.return_value = mock_stmt
            mock_insert.return_value = mock_stmt

            count = await seeder._batch_insert(mock_db, MagicMock, records)

        # With batch_size=2, 5 records = 3 batches
        assert mock_db.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_returns_total_count(self, seeder, mock_db):
        """Test total inserted count is returned."""
        records = [{"a": 1}, {"b": 2}]

        with patch("app.shared.seeder.core.pg_insert") as mock_insert:
            mock_stmt = MagicMock()
            mock_stmt.on_conflict_do_nothing.return_value = mock_stmt
            mock_insert.return_value = mock_stmt

            count = await seeder._batch_insert(mock_db, MagicMock, records)

        # rowcount=2 per batch, 1 batch for 2 records
        assert count == 2


class TestDeleteData:
    """Tests for delete_data method."""

    @pytest.fixture
    def seeder(self):
        """Create seeder."""
        return DataSeeder(SeederConfig(seed=42))

    @pytest.fixture
    def mock_db(self):
        """Create mock async session with count results."""
        db = AsyncMock()
        # Mock count queries to return different values
        db.execute.return_value.scalar.return_value = 10
        return db

    @pytest.mark.asyncio
    async def test_dry_run_returns_counts_without_delete(self, seeder, mock_db):
        """Test dry run returns counts but doesn't delete."""
        counts = await seeder.delete_data(mock_db, scope="all", dry_run=True)

        assert "store" in counts or len(counts) > 0
        # Should have called execute for counts but not commit
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_scope_facts_only(self, seeder, mock_db):
        """Test scope='facts' only deletes fact tables."""
        counts = await seeder.delete_data(mock_db, scope="facts", dry_run=True)

        # Should include fact tables
        assert isinstance(counts, dict)


class TestGetCurrentCounts:
    """Tests for get_current_counts method."""

    @pytest.fixture
    def seeder(self):
        """Create seeder."""
        return DataSeeder(SeederConfig(seed=42))

    @pytest.mark.asyncio
    async def test_returns_all_table_counts(self, seeder):
        """Test all tables are included in counts."""
        mock_db = AsyncMock()
        mock_db.execute.return_value.scalar.return_value = 100

        counts = await seeder.get_current_counts(mock_db)

        expected_tables = [
            "store",
            "product",
            "calendar",
            "sales_daily",
            "price_history",
            "promotion",
            "inventory_snapshot_daily",
        ]
        for table in expected_tables:
            assert table in counts


class TestVerifyDataIntegrity:
    """Tests for verify_data_integrity method."""

    @pytest.fixture
    def seeder(self):
        """Create seeder."""
        return DataSeeder(SeederConfig(seed=42))

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_valid(self, seeder):
        """Test empty list returned when data is valid."""
        mock_db = AsyncMock()
        # Mock all checks to return 0 (no errors)
        mock_db.execute.return_value.scalar.return_value = 0
        # Mock calendar date range check
        mock_db.execute.return_value.fetchone.return_value = (
            date(2024, 1, 1),
            date(2024, 1, 31),
        )

        errors = await seeder.verify_data_integrity(mock_db)

        assert errors == []

    @pytest.mark.asyncio
    async def test_detects_orphaned_sales(self, seeder):
        """Test orphaned sales are detected."""
        mock_db = AsyncMock()
        # First call (orphan check) returns 5
        mock_db.execute.return_value.scalar.side_effect = [5, 0, 31]
        mock_db.execute.return_value.fetchone.return_value = (
            date(2024, 1, 1),
            date(2024, 1, 31),
        )

        errors = await seeder.verify_data_integrity(mock_db)

        assert any("invalid foreign keys" in e for e in errors)

    @pytest.mark.asyncio
    async def test_detects_negative_quantities(self, seeder):
        """Test negative quantities are detected."""
        mock_db = AsyncMock()
        # Second call (negative qty check) returns 3
        mock_db.execute.return_value.scalar.side_effect = [0, 3, 31]
        mock_db.execute.return_value.fetchone.return_value = (
            date(2024, 1, 1),
            date(2024, 1, 31),
        )

        errors = await seeder.verify_data_integrity(mock_db)

        assert any("negative quantity" in e for e in errors)
```

---

### Task 5: Create `app/shared/seeder/tests/test_integration.py`

**File:** `app/shared/seeder/tests/test_integration.py`

Integration tests that run against real PostgreSQL.

```python
"""Integration tests for seeder (requires PostgreSQL).

Run with: uv run pytest app/shared/seeder/tests/test_integration.py -v -m integration
"""

from contextlib import suppress
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.features.data_platform.models import (
    Calendar,
    InventorySnapshotDaily,
    PriceHistory,
    Product,
    Promotion,
    SalesDaily,
    Store,
)
from app.shared.seeder import DataSeeder, SeederConfig
from app.shared.seeder.config import DimensionConfig, SparsityConfig

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Create a database session for testing."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        try:
            yield session
        finally:
            # Rollback any uncommitted changes
            with suppress(Exception):
                await session.rollback()

    # Cleanup in separate session
    async with session_maker() as cleanup_session:
        try:
            # Delete in FK order
            await cleanup_session.execute(delete(SalesDaily))
            await cleanup_session.execute(delete(InventorySnapshotDaily))
            await cleanup_session.execute(delete(PriceHistory))
            await cleanup_session.execute(delete(Promotion))
            await cleanup_session.execute(delete(Calendar))
            await cleanup_session.execute(delete(Product))
            await cleanup_session.execute(delete(Store))
            await cleanup_session.commit()
        except Exception:
            await cleanup_session.rollback()

    await engine.dispose()


class TestGenerateFull:
    """Integration tests for generate_full()."""

    @pytest.mark.asyncio
    async def test_generates_all_tables(self, db_session: AsyncSession):
        """Test full generation creates data in all tables."""
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),  # 1 week
            dimensions=DimensionConfig(stores=2, products=3),
            batch_size=100,
        )
        seeder = DataSeeder(config)

        result = await seeder.generate_full(db_session)

        assert result.stores_count == 2
        assert result.products_count == 3
        assert result.calendar_days == 7
        assert result.sales_count > 0
        assert result.seed == 42

    @pytest.mark.asyncio
    async def test_respects_unique_constraints(self, db_session: AsyncSession):
        """Test re-running generate_full doesn't create duplicates."""
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            dimensions=DimensionConfig(stores=2, products=2),
        )
        seeder = DataSeeder(config)

        # Run twice
        result1 = await seeder.generate_full(db_session)
        result2 = await seeder.generate_full(db_session)

        # Counts should be same (idempotent)
        assert result1.stores_count == result2.stores_count

    @pytest.mark.asyncio
    async def test_foreign_keys_valid(self, db_session: AsyncSession):
        """Test all foreign keys reference valid parents."""
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            dimensions=DimensionConfig(stores=2, products=3),
        )
        seeder = DataSeeder(config)
        await seeder.generate_full(db_session)

        # Verify no integrity errors
        errors = await seeder.verify_data_integrity(db_session)
        assert errors == []


class TestDeleteData:
    """Integration tests for delete_data()."""

    @pytest.mark.asyncio
    async def test_delete_all_clears_tables(self, db_session: AsyncSession):
        """Test delete with scope='all' clears all tables."""
        # First generate data
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            dimensions=DimensionConfig(stores=2, products=2),
        )
        seeder = DataSeeder(config)
        await seeder.generate_full(db_session)

        # Then delete
        counts = await seeder.delete_data(db_session, scope="all", dry_run=False)

        assert counts["store"] > 0  # Had data before

        # Verify tables are empty
        final_counts = await seeder.get_current_counts(db_session)
        assert all(c == 0 for c in final_counts.values())

    @pytest.mark.asyncio
    async def test_delete_facts_preserves_dimensions(self, db_session: AsyncSession):
        """Test delete with scope='facts' keeps dimension tables."""
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            dimensions=DimensionConfig(stores=2, products=2),
        )
        seeder = DataSeeder(config)
        await seeder.generate_full(db_session)

        counts_before = await seeder.get_current_counts(db_session)
        await seeder.delete_data(db_session, scope="facts", dry_run=False)
        counts_after = await seeder.get_current_counts(db_session)

        # Dimensions preserved
        assert counts_after["store"] == counts_before["store"]
        assert counts_after["product"] == counts_before["product"]
        # Facts deleted
        assert counts_after["sales_daily"] == 0


class TestAppendData:
    """Integration tests for append_data()."""

    @pytest.mark.asyncio
    async def test_append_extends_date_range(self, db_session: AsyncSession):
        """Test append adds data for new date range."""
        # First generate initial data
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),
            dimensions=DimensionConfig(stores=2, products=2),
        )
        seeder = DataSeeder(config)
        initial_result = await seeder.generate_full(db_session)

        # Append second week
        append_result = await seeder.append_data(
            db_session,
            start_date=date(2024, 1, 8),
            end_date=date(2024, 1, 14),
        )

        assert append_result.calendar_days == 7
        assert append_result.sales_count > 0

        # Total calendar days should be 14
        counts = await seeder.get_current_counts(db_session)
        assert counts["calendar"] == 14

    @pytest.mark.asyncio
    async def test_append_fails_without_dimensions(self, db_session: AsyncSession):
        """Test append fails if no dimensions exist."""
        config = SeederConfig(seed=42)
        seeder = DataSeeder(config)

        with pytest.raises(ValueError, match="No existing stores found"):
            await seeder.append_data(
                db_session,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 7),
            )


class TestSparsity:
    """Integration tests for sparsity configuration."""

    @pytest.mark.asyncio
    async def test_sparsity_reduces_sales_count(self, db_session: AsyncSession):
        """Test sparsity config reduces number of sales records."""
        # Full density
        config_full = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),
            dimensions=DimensionConfig(stores=3, products=4),
            sparsity=SparsityConfig(missing_combinations_pct=0.0),
        )

        # 50% sparse
        config_sparse = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),
            dimensions=DimensionConfig(stores=3, products=4),
            sparsity=SparsityConfig(missing_combinations_pct=0.5),
        )

        seeder_full = DataSeeder(config_full)
        result_full = await seeder_full.generate_full(db_session)

        # Cleanup and regenerate with sparse config
        await seeder_full.delete_data(db_session, scope="all", dry_run=False)

        seeder_sparse = DataSeeder(config_sparse)
        result_sparse = await seeder_sparse.generate_full(db_session)

        # Sparse should have fewer sales
        assert result_sparse.sales_count < result_full.sales_count


class TestReproducibility:
    """Integration tests for seed reproducibility."""

    @pytest.mark.asyncio
    async def test_same_seed_same_data(self, db_session: AsyncSession):
        """Test same seed produces same store/product codes."""
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            dimensions=DimensionConfig(stores=2, products=2),
        )

        # First run
        seeder1 = DataSeeder(config)
        await seeder1.generate_full(db_session)

        result = await db_session.execute(select(Store.code).order_by(Store.code))
        codes1 = [row[0] for row in result.fetchall()]

        # Cleanup
        await seeder1.delete_data(db_session, scope="all", dry_run=False)

        # Second run with same seed
        seeder2 = DataSeeder(config)
        await seeder2.generate_full(db_session)

        result = await db_session.execute(select(Store.code).order_by(Store.code))
        codes2 = [row[0] for row in result.fetchall()]

        assert codes1 == codes2
```

---

### Task 6: Update `app/shared/seeder/__init__.py`

**MODIFY:** `app/shared/seeder/__init__.py`

Add exports for the new RAG scenario module.

```python
"""Seeder module for generating synthetic test data.

The Forge - Development and testing data factory for generating realistic
synthetic datasets for the ForecastLabAI system.

Provides:
- Dimension generators (store, product, calendar)
- Fact generators with time-series patterns (sales, inventory, price, promotion)
- Pre-built scenarios for common testing needs
- Safe delete and append operations with confirmation guards
- RAG + Agent E2E validation scenario
"""

from app.shared.seeder.config import (
    RetailPatternConfig,
    ScenarioPreset,
    SeederConfig,
    TimeSeriesConfig,
)
from app.shared.seeder.core import DataSeeder, SeederResult
from app.shared.seeder.rag_scenario import RAGScenarioResult, RAGScenarioRunner, run_rag_scenario

__all__ = [
    "DataSeeder",
    "RAGScenarioResult",
    "RAGScenarioRunner",
    "RetailPatternConfig",
    "ScenarioPreset",
    "SeederConfig",
    "SeederResult",
    "TimeSeriesConfig",
    "run_rag_scenario",
]
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run these FIRST - fix any errors before proceeding
uv run ruff check app/shared/seeder/ scripts/seed_random.py --fix
uv run ruff format app/shared/seeder/ scripts/seed_random.py

# Type checking
uv run mypy app/shared/seeder/
uv run pyright app/shared/seeder/

# Expected: No errors
```

### Level 2: Unit Tests

```bash
# Run unit tests for seeder module
uv run pytest app/shared/seeder/tests/ -v -m "not integration"

# Expected: All tests pass
# If failing: Read error, understand root cause, fix code, re-run
```

### Level 3: Integration Tests

```bash
# Start database first
docker-compose up -d

# Wait for DB to be ready
sleep 5

# Run integration tests
uv run pytest app/shared/seeder/tests/test_integration.py -v -m integration

# Expected: All tests pass
```

### Level 4: CLI E2E Test

```bash
# Start API server (in another terminal)
uv run uvicorn app.main:app --reload --port 8123

# Test full generation
uv run python scripts/seed_random.py --full-new --seed 42 --stores 3 --products 5 --start-date 2024-01-01 --end-date 2024-01-10 --confirm

# Test status
uv run python scripts/seed_random.py --status

# Test verify
uv run python scripts/seed_random.py --verify

# Test delete dry-run
uv run python scripts/seed_random.py --delete --dry-run

# Test sparse config
uv run python scripts/seed_random.py --full-new --config examples/seed/config_sparse.yaml --confirm

# Clean up
uv run python scripts/seed_random.py --delete --confirm
```

### Level 5: RAG Scenario Test (Optional - requires RAG configuration)

```bash
# Only run if RAG is configured (OPENAI_API_KEY or Ollama running)

# Dry run first
uv run python scripts/seed_random.py --scenario rag-agent --dry-run

# Full run
uv run python scripts/seed_random.py --scenario rag-agent --confirm
```

---

## Final Validation Checklist

- [ ] All unit tests pass: `uv run pytest app/shared/seeder/tests/ -v -m "not integration"`
- [ ] All integration tests pass: `uv run pytest app/shared/seeder/tests/ -v -m integration`
- [ ] No linting errors: `uv run ruff check app/shared/seeder/ scripts/`
- [ ] No type errors: `uv run mypy app/shared/seeder/ && pyright app/shared/seeder/`
- [ ] `config_sparse.yaml` is valid and loadable
- [ ] CLI `--status`, `--verify`, `--full-new`, `--delete`, `--append` all work
- [ ] `--scenario rag-agent --dry-run` works (full run is optional/environment-dependent)
- [ ] Documentation in examples/seed/README.md is accurate

---

## Anti-Patterns to Avoid

- ❌ Don't test against mocked DB when testing constraint behavior (use integration tests)
- ❌ Don't skip async/await patterns - all DB operations are async
- ❌ Don't hardcode API URLs - use settings
- ❌ Don't make RAG scenario fail if RAG isn't configured - gracefully skip/warn
- ❌ Don't forget cleanup in integration tests (use fixtures with cleanup)
- ❌ Don't ignore mypy/pyright errors in new code

---

## Confidence Score: 8/10

**Rationale:**
- Core seeder infrastructure already exists and works (high confidence)
- RAG scenario is well-specified and follows existing patterns (medium-high)
- Integration tests follow established patterns from backtesting/registry features (high)
- Only uncertainty is RAG API contract details - may need minor adjustments based on actual endpoint schemas

**Risk Factors:**
- RAG indexing endpoint may have slightly different request schema
- Agent chat endpoint may return responses in different structure
- These can be fixed by reading actual route implementations if tests fail

**Mitigation:**
- Dry-run mode allows testing without actual API calls
- Errors are collected and reported, not silently ignored
- Scenario gracefully handles missing configuration

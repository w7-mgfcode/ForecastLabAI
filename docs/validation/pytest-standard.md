# Pytest Standard: Testing Configuration and Best Practices

## Overview

This project uses **pytest** as the testing framework with async support via `pytest-asyncio`. Pytest provides a simple, powerful, and extensible testing experience with minimal boilerplate.

**Why Pytest:**
- 🎯 Simple, Pythonic syntax (no classes required)
- ⚡️ Fast test execution and discovery
- 🔌 Rich plugin ecosystem
- 🤖 AI-friendly: clear assertions, minimal magic

## Configuration

All pytest configuration is in `pyproject.toml` under `[tool.pytest.ini_options]`.

### Core Settings

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["app", "tests"]
markers = [
    "integration: marks tests requiring real database (deselect with '-m \"not integration\"')",
]
```

- **asyncio_mode = "auto"**: Automatically creates new event loop per test (proper isolation)
- **testpaths**: Look for tests in `app/` and `tests/` directories
- **markers**: Custom markers for test categorization

## Test Discovery

Pytest discovers tests automatically:

### File Patterns

- **Test files**: `test_*.py` or `*_test.py`
- **Test functions**: `test_*()`
- **Test classes**: `Test*` with `test_*()` methods
- **Test locations**: Any directory in `testpaths`

### Examples

```
app/
├── core/
│   ├── tests/
│   │   ├── test_logging.py      ✅ Discovered
│   │   ├── test_middleware.py   ✅ Discovered
│   │   └── conftest.py          ✅ Fixtures loaded
│   ├── logging.py
│   └── middleware.py
└── shared/
    ├── tests/
    │   └── test_utils.py         ✅ Discovered
    └── utils.py

tests/
├── test_main.py                  ✅ Discovered
├── integration/
│   └── test_database_integration.py  ✅ Discovered
└── conftest.py                   ✅ Fixtures loaded
```

## Test Structure

### Basic Test

```python
def test_addition():
    """Test simple addition."""
    result = 1 + 1
    assert result == 2
```

### Async Test

```python
import pytest

@pytest.mark.asyncio
async def test_async_operation():
    """Test async function."""
    result = await fetch_data()
    assert result is not None
```

### Test with Fixtures

```python
import pytest

@pytest.fixture
def user_data():
    """Provide test user data."""
    return {"email": "test@example.com", "age": 25}

def test_user_creation(user_data):
    """Test user creation with fixture."""
    user = create_user(**user_data)
    assert user.email == user_data["email"]
    assert user.age == user_data["age"]
```

### Parameterized Tests

```python
import pytest

@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
])
def test_double(input, expected):
    """Test doubling function with multiple inputs."""
    assert double(input) == expected
```

## Async Testing

### Automatic Event Loop (asyncio_mode = "auto")

```python
import pytest

# No decorator needed! pytest-asyncio handles it automatically
async def test_database_query():
    """Test database query."""
    async with get_db_session() as session:
        result = await session.execute(select(User).where(User.id == 1))
        user = result.scalar_one_or_none()
        assert user is not None
```

### Manual Event Loop Control

```python
import pytest

@pytest.mark.asyncio
async def test_with_explicit_marker():
    """Test with explicit asyncio marker."""
    result = await async_operation()
    assert result == expected
```

### Async Fixtures

```python
import pytest

@pytest.fixture
async def database_session():
    """Provide database session for tests."""
    async with get_db_session() as session:
        yield session
        await session.rollback()  # Clean up after test

async def test_with_db(database_session):
    """Test using async database fixture."""
    result = await database_session.execute(select(User))
    users = result.scalars().all()
    assert len(users) >= 0
```

## Custom Markers

### Integration Tests

```python
import pytest

@pytest.mark.integration
async def test_database_connection():
    """Test real database connection."""
    async with get_db_session() as session:
        result = await session.execute(text("SELECT 1"))
        assert result is not None
```

Run only integration tests:
```bash
uv run pytest -m integration
```

Skip integration tests:
```bash
uv run pytest -m "not integration"
```

### Creating Custom Markers

Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = [
    "integration: marks tests requiring real database",
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "api: marks tests that hit external APIs",
]
```

Use in tests:
```python
import pytest

@pytest.mark.slow
def test_large_dataset():
    """Test with large dataset (slow)."""
    process_million_records()

@pytest.mark.api
async def test_external_api():
    """Test external API call."""
    response = await call_external_api()
    assert response.status_code == 200
```

## Fixtures

### Built-in Fixtures

```python
def test_with_tmp_path(tmp_path):
    """Test using temporary directory."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("content")
    assert file_path.read_text() == "content"

def test_with_capsys(capsys):
    """Test capturing stdout/stderr."""
    print("hello")
    captured = capsys.readouterr()
    assert captured.out == "hello\n"

def test_with_monkeypatch(monkeypatch):
    """Test with environment variable."""
    monkeypatch.setenv("API_KEY", "test-key")
    assert os.environ["API_KEY"] == "test-key"
```

### Custom Fixtures

```python
# conftest.py
import pytest

@pytest.fixture
def app():
    """Create FastAPI test application."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)

@pytest.fixture
def mock_settings():
    """Provide mock settings."""
    return Settings(
        app_name="Test App",
        environment="testing",
        database_url="sqlite:///:memory:",
    )

@pytest.fixture(scope="session")
def database_engine():
    """Create database engine for entire test session."""
    engine = create_engine("sqlite:///:memory:")
    yield engine
    engine.dispose()
```

### Fixture Scopes

| Scope | Lifecycle | Use Case |
|-------|-----------|----------|
| `function` | Per test (default) | Most fixtures |
| `class` | Per test class | Shared setup for class |
| `module` | Per test file | Expensive setup (DB connection) |
| `session` | Entire test run | One-time setup (test database) |

```python
@pytest.fixture(scope="session")
def expensive_resource():
    """Created once for entire test session."""
    resource = create_expensive_resource()
    yield resource
    resource.cleanup()
```

### Autouse Fixtures

```python
@pytest.fixture(autouse=True)
def reset_state():
    """Automatically run before each test."""
    clear_cache()
    reset_global_state()
    yield
    # Cleanup after test
```

## Assertions

### Basic Assertions

```python
# Equality
assert result == expected

# Inequality
assert result != unexpected

# Truthy/Falsy
assert value
assert not empty_value

# Membership
assert item in collection
assert key not in dictionary

# Type checking
assert isinstance(value, int)
assert isinstance(user, User)
```

### Detailed Assertions

```python
# Pytest provides detailed failure messages
assert user.email == "test@example.com"
# If fails: AssertionError: assert 'wrong@example.com' == 'test@example.com'

assert len(items) == 5
# If fails: AssertionError: assert 3 == 5
#  +  where 3 = len([1, 2, 3])
```

### Exception Testing

```python
import pytest

# Assert exception is raised
def test_division_by_zero():
    """Test that division by zero raises ValueError."""
    with pytest.raises(ValueError):
        divide(10, 0)

# Assert exception message
def test_not_found_error():
    """Test error message."""
    with pytest.raises(HTTPException) as exc_info:
        raise HTTPException(status_code=404, detail="User not found")

    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value.detail).lower()
```

### Approximate Comparisons

```python
# Float comparison with tolerance
assert result == pytest.approx(expected, rel=1e-5)

# Example
assert 0.1 + 0.2 == pytest.approx(0.3)
```

## Mocking and Patching

### Using unittest.mock

```python
from unittest.mock import patch, MagicMock, AsyncMock

def test_with_mock():
    """Test with mocked function."""
    with patch("app.core.external_api.call") as mock_call:
        mock_call.return_value = {"status": "success"}

        result = process_api_call()

        mock_call.assert_called_once()
        assert result["status"] == "success"

# Async mock
async def test_async_mock():
    """Test with async mock."""
    with patch("app.core.service.fetch_data") as mock_fetch:
        mock_fetch.return_value = AsyncMock(return_value={"data": "value"})

        result = await process_data()

        assert result["data"] == "value"
```

### Pytest Monkeypatch

```python
def test_with_monkeypatch(monkeypatch):
    """Test with monkeypatch."""
    # Patch environment variable
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

    # Patch attribute
    monkeypatch.setattr("app.core.config.Settings.debug", True)

    # Patch function
    def mock_get_user():
        return User(id=1, email="test@example.com")

    monkeypatch.setattr("app.services.get_user", mock_get_user)
```

## Running Tests

### Basic Commands

```bash
# Run all tests
uv run pytest

# Verbose output
uv run pytest -v

# Very verbose (show all output)
uv run pytest -vv

# Show print statements
uv run pytest -s

# Stop on first failure
uv run pytest -x

# Run last failed tests
uv run pytest --lf
```

### Selecting Tests

```bash
# Run specific file
uv run pytest app/core/tests/test_logging.py

# Run specific test
uv run pytest app/core/tests/test_logging.py::test_function_name

# Run by keyword
uv run pytest -k "logging"

# Run by marker
uv run pytest -m integration
uv run pytest -m "not integration"

# Run multiple markers
uv run pytest -m "integration and slow"
```

### Output Options

```bash
# Quiet (minimal output)
uv run pytest -q

# Show locals on failure
uv run pytest -l

# Show test summary
uv run pytest --tb=short  # Short traceback
uv run pytest --tb=line   # One line per failure
uv run pytest --tb=no     # No traceback
```

### Coverage

```bash
# Run with coverage
uv run pytest --cov=app

# Generate HTML coverage report
uv run pytest --cov=app --cov-report=html

# Coverage with missing lines
uv run pytest --cov=app --cov-report=term-missing

# Minimum coverage threshold
uv run pytest --cov=app --cov-fail-under=80
```

## Test Organization

### Directory Structure

```
app/
├── core/
│   ├── tests/
│   │   ├── conftest.py          # Fixtures for core tests
│   │   ├── test_logging.py
│   │   ├── test_middleware.py
│   │   └── test_database.py
│   ├── logging.py
│   ├── middleware.py
│   └── database.py
└── shared/
    ├── tests/
    │   └── test_utils.py
    └── utils.py

tests/
├── conftest.py                   # Global fixtures
├── test_main.py                  # Application-level tests
└── integration/
    ├── conftest.py               # Integration-specific fixtures
    └── test_database_integration.py
```

### Naming Conventions

- **Test files**: `test_<module>.py` (e.g., `test_logging.py`)
- **Test functions**: `test_<feature>_<scenario>` (e.g., `test_user_creation_with_valid_data`)
- **Test classes**: `Test<Feature>` (e.g., `TestUserRegistration`)
- **Fixtures**: Descriptive names (e.g., `user_data`, `mock_database_session`)

### Test Docstrings

```python
def test_user_registration_with_valid_email():
    """Test that user can register with valid email address.

    This test verifies:
    - Email validation passes
    - User is created in database
    - Confirmation email is sent
    """
    # Test implementation
```

## FastAPI Testing

### Test Client

```python
from fastapi.testclient import TestClient

from app.main import app

@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)

def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "Obsidian Agent Project"

def test_post_endpoint(client):
    """Test POST endpoint."""
    data = {"email": "test@example.com", "name": "Test User"}
    response = client.post("/users", json=data)
    assert response.status_code == 201
    assert response.json()["email"] == data["email"]
```

### Async Tests with Database

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import User

@pytest.mark.integration
async def test_user_creation():
    """Test creating user in database."""
    async with get_db() as session:
        user = User(email="test@example.com", age=25)
        session.add(user)
        await session.commit()
        await session.refresh(user)

        assert user.id is not None
        assert user.email == "test@example.com"
```

## Debugging Tests

### Using pdb

```python
def test_with_debugger():
    """Test with debugger."""
    result = calculate_complex_value()
    import pdb; pdb.set_trace()  # Breakpoint
    assert result == expected
```

Run with:
```bash
uv run pytest -s  # -s to see pdb output
```

### Print Debugging

```python
def test_with_print(capsys):
    """Test with print statements."""
    value = calculate_value()
    print(f"Calculated value: {value}")  # Will be captured

    # Access captured output
    captured = capsys.readouterr()
    print(captured.out)
```

Run with `-s` to see prints:
```bash
uv run pytest -s
```

## Best Practices

### ✅ DO

- Write descriptive test names
- Use fixtures for common setup
- Test edge cases and error conditions
- Use markers to categorize tests
- Keep tests fast (<1s for unit tests)
- Write integration tests for database/API
- Use `pytest.mark.parametrize` for similar tests
- Mock external dependencies
- Assert on behavior, not implementation
- Run tests frequently during development

### ❌ DON'T

- Write tests that depend on execution order
- Use `sleep()` in tests (use mocks/fixtures)
- Test implementation details
- Write flaky tests
- Skip tests without documenting why
- Mix unit and integration concerns
- Use complex logic in tests
- Share mutable state between tests
- Ignore test failures
- Write tests without assertions

## Common Patterns

### Testing Exceptions

```python
def test_invalid_input_raises_error():
    """Test that invalid input raises ValueError."""
    with pytest.raises(ValueError, match="Invalid email"):
        validate_email("not-an-email")
```

### Testing Async Code

```python
async def test_async_database_query():
    """Test async database query."""
    async with get_db() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        assert len(users) >= 0
```

### Testing Logging

```python
def test_logging_output(caplog):
    """Test that function logs correctly."""
    with caplog.at_level(logging.INFO):
        process_data()

    assert "user.registration_started" in caplog.text
    assert "user.registration_completed" in caplog.text
```

### Testing with Temp Files

```python
def test_file_processing(tmp_path):
    """Test file processing."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")

    result = process_file(test_file)

    assert result == "processed: test content"
```

## CI/CD Integration

```yaml
# .github/workflows/ci.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - name: Install dependencies
        run: uv sync
      - name: Run tests
        run: uv run pytest -v --cov=app --cov-report=term-missing
      - name: Run integration tests
        run: uv run pytest -v -m integration
        env:
          DATABASE_URL: postgresql://user:pass@localhost/test
```

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Pytest Fixtures](https://docs.pytest.org/en/stable/fixture.html)
- [Pytest Parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html)

---

**Last Updated:** 2025-10-29
**Pytest Version:** 8.4.2+
**Python Version:** 3.12+

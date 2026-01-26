# MyPy Standard: Static Type Checking Configuration

## Overview

This project uses **MyPy** for static type checking with strict mode enabled. MyPy verifies that type annotations are correct and catches type-related bugs before runtime.

**Why MyPy:**
- 🐛 Catch type errors at development time
- 📝 Enforce consistent type annotations
- 🔒 Prevent common bugs (None access, attribute errors)
- 🤖 AI-friendly: clear contracts for code generation

## Philosophy

**TYPE SAFETY IS NON-NEGOTIABLE**

- All functions must have complete type annotations
- Strict mode enabled by default
- No `Any` types without explicit justification
- Test files have relaxed rules (pragmatic strictness)

## Configuration

All MyPy configuration is in `pyproject.toml` under `[tool.mypy]`.

### Core Settings

```toml
[tool.mypy]
python_version = "3.12"
strict = true
show_error_codes = true
warn_unused_ignores = true
```

- **python_version = "3.12"**: Target Python 3.12+ syntax
- **strict = true**: Enable all strict type checking options
- **show_error_codes**: Display error codes (e.g., `[arg-type]`) for easier research
- **warn_unused_ignores**: Flag unnecessary `# type: ignore` comments

### Strict Mode Details

`strict = true` enables:

| Flag | Effect |
|------|--------|
| `disallow_untyped_defs` | All functions must have type annotations |
| `disallow_incomplete_defs` | Return types and all parameters must be typed |
| `check_untyped_defs` | Type-check function bodies even if signature isn't typed |
| `disallow_untyped_calls` | Can't call untyped functions from typed code |
| `disallow_any_unimported` | Disallow `Any` from missing imports |
| `disallow_any_expr` | Disallow `Any` in expressions |
| `disallow_any_decorated` | Disallow `Any` on decorated functions |
| `disallow_any_explicit` | Disallow explicit `Any` |
| `disallow_subclassing_any` | Can't subclass `Any` |
| `warn_return_any` | Warn when returning `Any` from typed function |
| `warn_redundant_casts` | Warn about unnecessary type casts |
| `warn_unused_ignores` | Warn about unnecessary `# type: ignore` |
| `warn_no_return` | Warn if function doesn't return but should |
| `warn_unreachable` | Warn about unreachable code |

### Practical Adjustments

```toml
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
disallow_untyped_decorators = false
```

- **disallow_untyped_decorators = false**: FastAPI decorators aren't typed; this would break `@app.get()`

### Test File Overrides

```toml
[[tool.mypy.overrides]]
module = "*.tests.*"
disallow_untyped_defs = false

[[tool.mypy.overrides]]
module = "test_*"
disallow_untyped_defs = false
```

Test files don't require complete type annotations:
- Fixtures often have complex types
- Test functions are self-documenting
- Pragmatic balance between safety and velocity

## Usage

### Check All Files

```bash
# Check entire project
uv run mypy app/

# Check specific file
uv run mypy app/main.py

# Check specific directory
uv run mypy app/core/
```

### Common Output

```bash
$ uv run mypy app/
Success: no issues found in 29 source files
```

## Type Annotation Patterns

### Function Signatures

```python
# ✅ Complete annotation
def create_user(email: str, age: int) -> User:
    return User(email=email, age=age)

# ✅ Optional parameters
def greet(name: str, title: str | None = None) -> str:
    if title:
        return f"Hello, {title} {name}"
    return f"Hello, {name}"

# ✅ Multiple return types
def find_user(user_id: int) -> User | None:
    user = db.query(User).filter_by(id=user_id).first()
    return user

# ❌ Missing return type
def process_data(items: list[str]):  # Error: missing return type
    return [item.upper() for item in items]

# ❌ Incomplete parameters
def calculate(a, b: int) -> int:  # Error: 'a' missing type
    return a + b
```

### Async Functions

```python
from typing import AsyncIterator

# ✅ Async function
async def fetch_user(user_id: int) -> User:
    async with db_session() as session:
        return await session.get(User, user_id)

# ✅ Async generator
async def stream_data() -> AsyncIterator[bytes]:
    async for chunk in data_source:
        yield chunk
```

### Collections

```python
from collections.abc import Sequence, Mapping

# ✅ List with specific type
def process_emails(emails: list[str]) -> None:
    pass

# ✅ Dict with key and value types
def get_config() -> dict[str, int]:
    return {"timeout": 30, "retries": 3}

# ✅ Generic collection types
def process_items(items: Sequence[str]) -> None:
    # Works with list, tuple, etc.
    pass

# ✅ Nested generics
def group_by_category() -> dict[str, list[Product]]:
    return {"electronics": [laptop, phone]}
```

### Type Aliases

```python
from typing import TypeAlias

# ✅ Reusable type alias
UserId: TypeAlias = int
Email: TypeAlias = str
UserDict: TypeAlias = dict[str, str | int]

def create_user(user_id: UserId, email: Email) -> UserDict:
    return {"id": user_id, "email": email, "active": True}
```

### Generic Types

```python
from typing import Generic, TypeVar

T = TypeVar("T")

class Repository(Generic[T]):
    def get(self, id: int) -> T | None:
        pass

    def list(self) -> list[T]:
        pass

# Usage
user_repo: Repository[User] = Repository()
user: User | None = user_repo.get(1)
```

### TypedDict

```python
from typing import TypedDict

class UserData(TypedDict):
    id: int
    email: str
    active: bool

def process_user(data: UserData) -> None:
    print(data["email"])  # Type-safe key access
```

## Common Patterns

### FastAPI Endpoints

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas import UserCreate, UserResponse

router = APIRouter()

@router.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> User:
    user = User(**user_data.model_dump())
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
```

### Pydantic Models

```python
from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    email: EmailStr
    age: int

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    age: int

# Pydantic handles validation, MyPy handles type checking
def create_user(data: UserCreate) -> UserResponse:
    # MyPy knows data.email is EmailStr
    # MyPy knows we must return UserResponse
    pass
```

### SQLAlchemy Models

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    age: Mapped[int]

    # MyPy understands Mapped[T] types
```

### Context Managers

```python
from types import TracebackType
from typing import Self

class DatabaseConnection:
    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

# Async context manager
class AsyncDatabaseConnection:
    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()
```

## Handling Type Errors

### Fixing "incompatible type" errors

```python
# ❌ Error: Incompatible types in assignment
def get_user_id() -> int:
    user_id: str = "123"  # Error: str incompatible with int
    return user_id

# ✅ Fixed
def get_user_id() -> int:
    user_id: int = 123
    return user_id

# ✅ Or convert explicitly
def get_user_id() -> int:
    user_id_str: str = "123"
    return int(user_id_str)
```

### Handling None

```python
# ❌ Error: "User | None" has no attribute "email"
def get_user_email(user_id: int) -> str:
    user: User | None = find_user(user_id)
    return user.email  # Error: user might be None

# ✅ Fixed with guard
def get_user_email(user_id: int) -> str | None:
    user: User | None = find_user(user_id)
    if user is None:
        return None
    return user.email

# ✅ Or raise exception
def get_user_email(user_id: int) -> str:
    user: User | None = find_user(user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found")
    return user.email
```

### Type Narrowing

```python
def process_value(value: str | int) -> str:
    if isinstance(value, str):
        # MyPy knows value is str here
        return value.upper()
    else:
        # MyPy knows value is int here
        return str(value * 2)
```

### Dealing with `Any`

```python
from typing import Any, cast

# ❌ Avoid Any when possible
def process(data: Any) -> Any:
    return data

# ✅ Use specific types
def process(data: dict[str, str]) -> list[str]:
    return list(data.values())

# ⚠️ If Any is unavoidable, document why
def process_external_api(response: Any) -> dict[str, Any]:
    """Process external API response.

    Args:
        response: External API response with dynamic structure.
                  Type: Any because structure varies by endpoint.
    """
    # Document why Any is necessary
    return cast(dict[str, Any], response["data"])
```

## Type Ignores

Sometimes you need to suppress MyPy errors. Always document why.

```python
# ❌ Don't do this
result = unsafe_operation()  # type: ignore

# ✅ Do this
result = unsafe_operation()  # type: ignore[arg-type]  # External library lacks stubs

# ✅ Or explain in comment
result = unsafe_operation()  # type: ignore[arg-type]
# SQLAlchemy relationship() doesn't have proper typing yet
```

### Common Type Ignore Codes

| Code | Meaning | When to Use |
|------|---------|-------------|
| `[arg-type]` | Argument type mismatch | External library missing stubs |
| `[assignment]` | Assignment type mismatch | Complex generic types |
| `[return-value]` | Return type mismatch | Decorator interaction |
| `[attr-defined]` | Attribute not defined | Dynamic attributes |
| `[call-arg]` | Wrong number/type of args | Decorator or metaclass magic |

## Common Errors and Fixes

### Error: Function is missing a return type annotation

```python
# ❌ Error
def calculate_total(items):
    return sum(items)

# ✅ Fixed
def calculate_total(items: list[int]) -> int:
    return sum(items)
```

### Error: Need type annotation for 'x'

```python
# ❌ Error
def process_items():
    results = []  # Error: Need type annotation
    for i in range(10):
        results.append(i * 2)
    return results

# ✅ Fixed
def process_items() -> list[int]:
    results: list[int] = []
    for i in range(10):
        results.append(i * 2)
    return results
```

### Error: Argument has incompatible type

```python
# ❌ Error
def greet(name: str) -> str:
    return f"Hello, {name}"

greet(123)  # Error: Argument 1 has incompatible type "int"

# ✅ Fixed
greet(str(123))
# or
greet("123")
```

### Error: "X" has no attribute "Y"

```python
# ❌ Error
def get_config() -> dict[str, str]:
    return {"key": "value"}

config = get_config()
config.get_value()  # Error: dict has no attribute "get_value"

# ✅ Fixed - use correct method
value = config.get("key")

# ✅ Or create typed class
class Config:
    def __init__(self, key: str):
        self.key = key

    def get_value(self) -> str:
        return self.key
```

## Integration with CI/CD

```yaml
# .github/workflows/ci.yml
name: Type Check

on: [push, pull_request]

jobs:
  mypy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - name: Install dependencies
        run: uv sync
      - name: Run MyPy
        run: uv run mypy app/
```

## Editor Integration

### VS Code

Install Python extension and configure:

```json
{
  "python.linting.mypyEnabled": true,
  "python.linting.enabled": true
}
```

### PyCharm

MyPy is built-in. Enable at:
Settings → Editor → Inspections → Python → Type Checker → MyPy

## Performance Tips

MyPy can be slow on large codebases. Use caching:

```bash
# First run (slow)
uv run mypy app/

# Subsequent runs (fast - uses cache)
uv run mypy app/
```

Cache is stored in `.mypy_cache/`. Add to `.gitignore`.

## Updating MyPy

```bash
# Update to latest version
uv sync --upgrade-package mypy

# Or update all dev dependencies
uv sync --upgrade
```

## MyPy vs Pyright

This project uses **both** MyPy and Pyright for maximum type safety:

| Aspect | MyPy | Pyright |
|--------|------|---------|
| **Adoption** | Older, more mature | Newer, gaining adoption |
| **Speed** | Slower (Python) | Faster (Node.js/Rust) |
| **Strictness** | Pragmatic | Very strict |
| **Third-party** | More lenient | Catches edge cases |
| **Use Case** | Development | CI/CD gate |

Run both:
```bash
uv run mypy app/ && uv run pyright app/
```

## Best Practices

### ✅ DO

- Add type hints to all new functions
- Use `str | None` instead of `Optional[str]` (Python 3.10+)
- Run MyPy frequently during development
- Fix MyPy errors before committing
- Document why `# type: ignore` is needed
- Use `reveal_type()` during debugging

### ❌ DON'T

- Use `Any` without documentation
- Add `# type: ignore` to silence errors without understanding
- Disable strict mode globally
- Skip type annotations "to save time" (costs more later)
- Mix type annotation styles in same file

## Debugging Type Issues

```python
from typing import reveal_type

def process(value: str | int) -> None:
    reveal_type(value)  # Revealed type is "str | int"

    if isinstance(value, str):
        reveal_type(value)  # Revealed type is "str"

    # MyPy will print these types during checking
```

## Resources

- [MyPy Documentation](https://mypy.readthedocs.io/)
- [MyPy Cheat Sheet](https://mypy.readthedocs.io/en/stable/cheat_sheet_py3.html)
- [PEP 484 - Type Hints](https://peps.python.org/pep-0484/)
- [Typing Module Docs](https://docs.python.org/3/library/typing.html)

---

**Last Updated:** 2025-10-29
**MyPy Version:** 1.18.2+
**Python Version:** 3.12+

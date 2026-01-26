# Pyright Standard: Advanced Type Checking Configuration

## Overview

This project uses **Pyright** as a second-layer type checker alongside MyPy. Pyright is Microsoft's static type checker for Python, written in TypeScript/Node.js, providing extremely fast and strict type analysis.

**Why Pyright + MyPy:**
- 🔍 Pyright catches edge cases MyPy misses
- ⚡️ Lightning fast (written in TypeScript)
- 🎯 Stricter variance and protocol checking
- 🛡️ Production-ready safety net

## Philosophy

**Dual-Layer Type Checking:**
1. **MyPy** - Pragmatic development (lenient with third-party)
2. **Pyright** - Strict production gate (catches subtle bugs)

Use Pyright as the **final check** before merging to main.

## Configuration

All Pyright configuration is in `pyproject.toml` under `[tool.pyright]`.

### Include/Exclude Paths

```toml
[tool.pyright]
include = ["app"]
exclude = [
    "**/__pycache__",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache"
]
```

- **include**: Only check `app/` directory
- **exclude**: Skip build artifacts and caches

### Python Version

```toml
pythonVersion = "3.12"
pythonPlatform = "Darwin"
```

- **pythonVersion**: Target Python 3.12 features
- **pythonPlatform**: OS-specific (Darwin/Linux/Windows) - adjust for your system

### Type Checking Mode

```toml
typeCheckingMode = "strict"
```

Pyright has three modes:
- **basic**: Minimal checking (default)
- **standard**: Reasonable balance
- **strict**: Maximum type safety ✅ (our choice)

### Strict Mode Settings

```toml
# Test files can have unused functions (fixtures, route handlers)
reportUnusedFunction = "none"
```

In strict mode, Pyright enables:
- All type annotations required
- No implicit `Any`
- Strict variance checking
- Protocol compliance
- Unknown/missing type stubs reported

We disable `reportUnusedFunction` because:
- Pytest fixtures appear unused
- FastAPI route handlers appear unused
- Test helper functions are intentionally defined

## What Pyright Catches That MyPy Doesn't

### 1. Variance Checking

```python
from collections.abc import MutableMapping

# MyPy: ✅ Passes
# Pyright: ❌ Error: dict[str, Any] not assignable to MutableMapping[str, Any]
def process(data: dict[str, Any]) -> MutableMapping[str, Any]:
    return data  # Pyright error: variance mismatch
```

**Why:** `dict` is invariant in key type, `MutableMapping` is covariant. Pyright enforces stricter subtyping rules.

### 2. Protocol Compliance

```python
from typing import Protocol

class Drawable(Protocol):
    def draw(self) -> None: ...

class Circle:
    def draw(self) -> str:  # Wrong return type
        return "circle"

# MyPy: Sometimes passes (implementation-dependent)
# Pyright: ❌ Error: Return type mismatch
def render(obj: Drawable) -> None:
    obj.draw()

render(Circle())  # Pyright catches this
```

### 3. Deprecated API Usage

```python
from typing import List  # Deprecated in Python 3.9+

# MyPy: ✅ Passes (lenient)
# Pyright: ⚠️ Warning: Use list[T] instead of List[T]
def process(items: List[str]) -> None:
    pass
```

### 4. Type Narrowing

```python
def process(value: str | None) -> str:
    if not value:
        return ""
    # MyPy: Might not narrow correctly
    # Pyright: Knows value is str here
    return value.upper()  # Pyright guarantees this is safe
```

### 5. Generic Constraints

```python
from typing import TypeVar

T = TypeVar("T", bound=int)

# MyPy: Might allow incorrect usage
# Pyright: Strictly enforces bound constraints
def double(x: T) -> T:
    return x * 2  # Pyright verifies T supports multiplication
```

## Usage

### Check All Files

```bash
# Check entire project
uv run pyright app/

# Check specific file
uv run pyright app/main.py

# Check specific directory
uv run pyright app/core/
```

### Expected Output

```bash
$ uv run pyright app/
0 errors, 0 warnings, 0 informations
```

### Common Output

```bash
# When there are errors
$ uv run pyright app/
app/core/middleware.py:45:5 - error: Argument type is partially unknown
app/models.py:12:9 - error: "dict[str, Any]" is not assignable to "MutableMapping[str, Any]"
2 errors, 0 warnings, 0 informations
```

## Strict Mode Checks

### reportMissingImports

```python
# ❌ Error: Cannot find module
import nonexistent_module
```

**Fix:** Install missing package or add to type stubs.

### reportMissingTypeStubs

```python
# ⚠️ Warning: No type stubs for third-party library
import some_untyped_library
```

**Options:**
1. Install stubs: `pip install types-some_untyped_library`
2. Create local stubs in `stubs/` directory
3. Add `# pyright: ignore[reportMissingTypeStubs]`

### reportUnusedImport

```python
# ❌ Error: Import is unused
from typing import List  # Not used in file
```

**Fix:** Remove unused import.

### reportUnusedVariable

```python
# ❌ Error: Variable is unused
def process():
    unused_var = 42  # Never used
    return True
```

**Fix:** Remove or use the variable.

### reportDuplicateImport

```python
# ❌ Error: Duplicate import
from typing import List
from typing import List  # Duplicate
```

**Fix:** Remove duplicate.

### reportOptionalMemberAccess

```python
# ❌ Error: Cannot access member on None
def get_email(user: User | None) -> str:
    return user.email  # Error: user might be None
```

**Fix:**
```python
def get_email(user: User | None) -> str:
    if user is None:
        return ""
    return user.email
```

### reportOptionalSubscript

```python
# ❌ Error: Cannot subscript None
def get_first(items: list[str] | None) -> str:
    return items[0]  # Error: items might be None
```

**Fix:**
```python
def get_first(items: list[str] | None) -> str:
    if items is None:
        return ""
    return items[0]
```

### reportUntypedFunctionDecorator

```python
# ⚠️ Warning: Decorator obscures type
@untyped_decorator
def process(x: int) -> int:
    return x * 2
```

**Fix:** Add type hints to decorator or use `# pyright: ignore`.

### reportUnknownParameterType

```python
# ❌ Error: Parameter type is unknown
def process(data):  # Missing type annotation
    pass
```

**Fix:**
```python
def process(data: dict[str, Any]) -> None:
    pass
```

### reportUnknownVariableType

```python
# ❌ Error: Variable type is unknown
result = external_function()  # Return type not annotated
```

**Fix:** Annotate the variable:
```python
result: dict[str, str] = external_function()
```

### reportIncompatibleMethodOverride

```python
class Base:
    def process(self, x: int) -> int:
        return x

class Derived(Base):
    # ❌ Error: Incompatible override
    def process(self, x: str) -> int:  # Parameter type changed
        return len(x)
```

**Fix:** Match base class signature or use `@override` decorator.

## Common Patterns

### FastAPI with Depends

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter()

# Pyright understands FastAPI dependency injection
@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    # Pyright knows db is AsyncSession
    result = await db.execute(...)
    return {"id": str(user_id)}
```

### Pydantic Models

```python
from pydantic import BaseModel

class User(BaseModel):
    id: int
    email: str

# Pyright understands Pydantic model fields
def process_user(user: User) -> str:
    # Pyright knows user.email is str
    return user.email.upper()
```

### SQLAlchemy Mapped

```python
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str]

# Pyright understands Mapped[T] properly
def get_user_email(user: User) -> str:
    return user.email  # Pyright knows this is str
```

## Suppressing Errors

### Inline Suppression

```python
# Suppress specific error
result = unsafe_call()  # pyright: ignore[reportUnknownVariableType]

# Suppress all errors on line
result = unsafe_call()  # pyright: ignore

# Suppress for entire file (top of file)
# pyright: reportUnknownVariableType=false
```

### Configuration Suppression

Don't do this unless absolutely necessary:

```toml
[tool.pyright]
reportUnknownVariableType = "none"  # ❌ Defeats the purpose
```

## Integration with CI/CD

```yaml
# .github/workflows/ci.yml
name: Type Check

on: [push, pull_request]

jobs:
  type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - name: Install dependencies
        run: uv sync
      - name: Run MyPy
        run: uv run mypy app/
      - name: Run Pyright
        run: uv run pyright app/
```

## Editor Integration

### VS Code

Install Pylance extension (includes Pyright):

```json
{
  "python.analysis.typeCheckingMode": "strict",
  "python.analysis.diagnosticMode": "workspace"
}
```

Pylance uses Pyright internally.

### PyCharm

PyCharm has built-in type checking. To use Pyright:

Settings → Tools → External Tools → Add Pyright

### Vim/Neovim

Use `pyright-langserver` with LSP client:

```lua
require('lspconfig').pyright.setup{
  settings = {
    python = {
      analysis = {
        typeCheckingMode = "strict"
      }
    }
  }
}
```

## MyPy vs Pyright: When to Use Which

### MyPy

- ✅ Development workflow (faster iteration)
- ✅ Lenient with third-party libraries
- ✅ More forgiving with decorators
- ✅ Established ecosystem

### Pyright

- ✅ Pre-merge checks (CI/CD gate)
- ✅ Catches subtle type errors
- ✅ Strict protocol compliance
- ✅ Production readiness verification

### Recommended Workflow

```bash
# During development (fast feedback)
uv run mypy app/

# Before committing (comprehensive check)
uv run mypy app/ && uv run pyright app/

# CI/CD pipeline (must pass both)
uv run mypy app/ && uv run pyright app/
```

## Performance

Pyright is extremely fast:

```bash
$ time uv run pyright app/
0 errors, 0 warnings, 0 informations
uv run pyright app/  0.89s user 0.13s system 105% cpu 0.970 total

$ time uv run mypy app/
Success: no issues found in 29 source files
uv run mypy app/  2.45s user 0.21s system 101% cpu 2.622 total
```

Pyright is typically **2-3x faster** than MyPy.

## Common Issues

### "Cannot find module" for installed package

**Cause:** Virtual environment not detected.

**Fix:**
```bash
# Ensure Pyright uses correct venv
uv run pyright app/

# Or create pyrightconfig.json
{
  "venvPath": ".",
  "venv": ".venv"
}
```

### Too many errors from strict mode

**Cause:** Codebase not fully typed.

**Options:**
1. Fix types incrementally (recommended)
2. Start with "standard" mode, move to "strict"
3. Suppress specific errors temporarily

### Conflicting with MyPy

**Cause:** Different interpretation of type spec.

**Resolution:**
- Follow Pyright (usually stricter/more correct)
- Document decision with comment
- Report to MyPy/Pyright if it's a bug

## Updating Pyright

```bash
# Update to latest version
uv sync --upgrade-package pyright

# Or update all dev dependencies
uv sync --upgrade
```

## Best Practices

### ✅ DO

- Run Pyright before merging to main
- Fix Pyright errors (don't suppress)
- Use strict mode for production code
- Keep Pyright and MyPy both passing
- Trust Pyright when it catches edge cases

### ❌ DON'T

- Disable strict mode globally
- Suppress errors without understanding
- Skip Pyright checks "to save time"
- Assume MyPy passing = fully type-safe
- Use Pyright as replacement for MyPy (use both)

## Debugging Type Issues

### reveal_type() Equivalent

Pyright doesn't support `reveal_type()` directly, but hover in VS Code shows types.

### Verbose Output

```bash
# More detailed output
uv run pyright app/ --verbose

# Output as JSON
uv run pyright app/ --outputjson
```

## Resources

- [Pyright Documentation](https://microsoft.github.io/pyright/)
- [Pyright Configuration Reference](https://microsoft.github.io/pyright/#/configuration)
- [Pylance (VS Code)](https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance)
- [Type Checking Mode Comparison](https://microsoft.github.io/pyright/#/configuration?id=type-checking-rule-overrides)

---

**Last Updated:** 2025-10-29
**Pyright Version:** 1.1.407+
**Python Version:** 3.12+

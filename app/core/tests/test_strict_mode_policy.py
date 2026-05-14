"""Strict-mode policy invariant test.

Codifies the Pydantic v2 ``ConfigDict(strict=True)`` + JSON-non-native-field
policy from ``docs/_base/SECURITY.md`` as a never-weaken pytest invariant.

Bug class precedent — same regression shipped twice in 14 days:
    - PR #115 (closing issue #109): ``ComputeFeaturesRequest.cutoff_date``,
      ``PreviewFeaturesRequest.cutoff_date``
    - PR #119 (closing issue #117): ``TrainRequest.train_start_date``,
      ``TrainRequest.train_end_date``

Policy: every FastAPI request-body Pydantic model with
``model_config = ConfigDict(strict=True)`` MUST annotate every field whose
type has no native JSON representation (``date | datetime | time | UUID |
Decimal``) with a field-level ``Field(strict=False, ...)`` override.
Without the override, FastAPI's ``validate_python`` path
(``fastapi._compat.v2:175``) refuses to coerce ISO-string JSON values into
the Python type, and every HTTP caller 422s.

AST-only by design: never imports the model classes at runtime, which would
couple this test to every slice's import graph and risk SQLAlchemy
registration side effects.

Mirror of the load-bearing ``app/features/featuresets/tests/test_leakage.py``
precedent — one file, opinionated, cited as a never-weaken spec.
"""

from __future__ import annotations

import ast
import textwrap
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Canonical names of JSON-non-native types that require ``Field(strict=False)``
# when the enclosing model has ``ConfigDict(strict=True)``.
TARGET_TYPES: frozenset[str] = frozenset({"date", "datetime", "time", "UUID", "Decimal"})

# Stdlib (module, attribute) -> canonical type name. Drives the import-alias
# resolver so ``from datetime import date as D`` maps ``D`` -> ``date``.
_STDLIB_TARGETS: dict[tuple[str, str], str] = {
    ("datetime", "date"): "date",
    ("datetime", "datetime"): "datetime",
    ("datetime", "time"): "time",
    ("uuid", "UUID"): "UUID",
    ("decimal", "Decimal"): "Decimal",
}

# ``app/features`` resolved from this file: ``app/core/tests/`` -> ``..`` -> ``app/`` -> ``features``.
_FEATURES_ROOT: Path = Path(__file__).resolve().parents[2] / "features"

# Baseline guard: the walker MUST discover these 4 known-good models on every
# run. Without this, an empty parametrize set would silently pass (vacuous-green).
_EXPECTED_STRICT_MODELS: frozenset[str] = frozenset(
    {
        "ComputeFeaturesRequest",
        "PreviewFeaturesRequest",
        "TrainRequest",
        "PredictRequest",
    }
)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldHit:
    """One field-level policy-check result discovered by the walker."""

    file: Path
    lineno: int
    model_name: str
    field_name: str
    resolved_type: str
    has_strict_false: bool

    @property
    def case_id(self) -> str:
        return f"{self.file.parent.name}/{self.file.name}::{self.model_name}::{self.field_name}"


# ---------------------------------------------------------------------------
# AST primitives
# ---------------------------------------------------------------------------


def _build_alias_map(tree: ast.Module) -> dict[str, str]:
    """Map local names in ``tree`` to canonical target-type names.

    Handles all four import idioms the codebase uses:

        from datetime import date              -> aliases["date"] = "date"
        from datetime import date as date_type -> aliases["date_type"] = "date"
        import datetime                        -> aliases["datetime.date"] = "date"
        import datetime as dt                  -> aliases["dt.date"] = "date"
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            for name in node.names:
                key = (node.module, name.name)
                if key in _STDLIB_TARGETS:
                    aliases[name.asname or name.name] = _STDLIB_TARGETS[key]
        elif isinstance(node, ast.Import):
            for name in node.names:
                local_root = name.asname or name.name
                for (mod, attr), target in _STDLIB_TARGETS.items():
                    if mod == name.name:
                        aliases[f"{local_root}.{attr}"] = target
    return aliases


def _call_callee_name(call: ast.Call) -> str | None:
    """Return the leaf-callable name (``Field``, ``ConfigDict``, ...) or None."""
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _call_has_bool_kwarg(call: ast.Call, name: str, expected: bool) -> bool:
    """True iff ``call`` has ``name=<expected>`` as a literal bool keyword."""
    for kw in call.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant) and kw.value.value is expected:
            return True
    return False


def _is_strict_config_dict_call(value: ast.expr | None) -> bool:
    """True if ``value`` is ``ConfigDict(...strict=True...)`` (other kwargs OK)."""
    return (
        isinstance(value, ast.Call)
        and _call_callee_name(value) == "ConfigDict"
        and _call_has_bool_kwarg(value, "strict", True)
    )


def _class_has_strict_config(cls: ast.ClassDef) -> bool:
    """True if the class body assigns ``model_config = ConfigDict(strict=True, ...)``.

    Handles both ``Assign`` and ``AnnAssign`` (e.g., ``model_config: ClassVar[...] = ...``).
    Does NOT follow inheritance — current codebase has no inherited-config pattern;
    see ``PRPs/PRP-14-strict-mode-policy-linter.md`` §6 for the scope limit.
    """
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "model_config"
                    and _is_strict_config_dict_call(stmt.value)
                ):
                    return True
        elif isinstance(stmt, ast.AnnAssign):
            if (
                isinstance(stmt.target, ast.Name)
                and stmt.target.id == "model_config"
                and _is_strict_config_dict_call(stmt.value)
            ):
                return True
    return False


def _annotation_target_type(annotation: ast.expr | None, aliases: dict[str, str]) -> str | None:
    """Return the first canonical target type found anywhere in ``annotation``.

    Walks the annotation subtree and matches any leaf ``Name`` or ``Attribute``
    against the alias map. Uniformly handles bare ``date``, ``Optional[date]``,
    ``date | None``, ``Annotated[date, ...]``, ``list[date]``, ``dict[K, date]``
    without per-form code.
    """
    if annotation is None:
        return None
    for sub in ast.walk(annotation):
        if isinstance(sub, ast.Name):
            target = aliases.get(sub.id)
            if target is not None and target in TARGET_TYPES:
                return target
        elif isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
            target = aliases.get(f"{sub.value.id}.{sub.attr}")
            if target is not None and target in TARGET_TYPES:
                return target
    return None


def _has_strict_false_override(field_stmt: ast.AnnAssign) -> bool:
    """True if the field carries ``Field(strict=False, ...)`` in either form:

    1. ``cutoff_date: date = Field(strict=False, ...)``  (default-value form)
    2. ``cutoff_date: Annotated[date, Field(strict=False, ...)]``  (annotated form)
    """
    if isinstance(field_stmt.value, ast.Call) and _call_callee_name(field_stmt.value) == "Field":
        if _call_has_bool_kwarg(field_stmt.value, "strict", False):
            return True

    annotation = field_stmt.annotation
    if isinstance(annotation, ast.Subscript):
        outer = annotation.value
        is_annotated = (isinstance(outer, ast.Name) and outer.id == "Annotated") or (
            isinstance(outer, ast.Attribute) and outer.attr == "Annotated"
        )
        if is_annotated:
            slice_node = annotation.slice
            elements: list[ast.expr] = (
                list(slice_node.elts) if isinstance(slice_node, ast.Tuple) else [slice_node]
            )
            for elt in elements[1:]:  # skip the type element (index 0)
                if (
                    isinstance(elt, ast.Call)
                    and _call_callee_name(elt) == "Field"
                    and _call_has_bool_kwarg(elt, "strict", False)
                ):
                    return True
    return False


# ---------------------------------------------------------------------------
# Walker iterators
# ---------------------------------------------------------------------------


def _iter_strict_request_models(
    features_root: Path,
) -> Iterator[tuple[Path, ast.ClassDef, dict[str, str]]]:
    """Walk ``app/features/*/schemas.py`` and yield strict-mode model classes."""
    for schema_file in sorted(features_root.glob("*/schemas.py")):
        tree = ast.parse(schema_file.read_text(encoding="utf-8"), filename=str(schema_file))
        aliases = _build_alias_map(tree)
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and _class_has_strict_config(node):
                yield schema_file, node, aliases


def _iter_json_non_native_fields(
    file: Path, cls: ast.ClassDef, aliases: dict[str, str]
) -> Iterator[FieldHit]:
    """Yield a ``FieldHit`` for every JSON-non-native field on ``cls``."""
    for stmt in cls.body:
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue
        target_type = _annotation_target_type(stmt.annotation, aliases)
        if target_type is None:
            continue
        yield FieldHit(
            file=file,
            lineno=stmt.lineno,
            model_name=cls.name,
            field_name=stmt.target.id,
            resolved_type=target_type,
            has_strict_false=_has_strict_false_override(stmt),
        )


def _discover_field_hits() -> list[FieldHit]:
    return [
        hit
        for file, cls, aliases in _iter_strict_request_models(_FEATURES_ROOT)
        for hit in _iter_json_non_native_fields(file, cls, aliases)
    ]


def _format_failure(hit: FieldHit) -> str:
    repo_root = _FEATURES_ROOT.parents[1]
    rel = hit.file.relative_to(repo_root)
    return (
        f"\n  {rel}:{hit.lineno}  {hit.model_name}.{hit.field_name}"
        f"  typed {hit.resolved_type}  needs Field(strict=False, ...)"
        f"\n  See docs/_base/SECURITY.md → 'Pydantic v2 strict mode on FastAPI request bodies'"
        f"\n  Fix pattern (mirrors PR #115 / PR #119):"
        f'\n      {hit.field_name}: {hit.resolved_type} = Field(strict=False, description="...")'
    )


# Discovered at module import so pytest can parametrize over the cases.
_FIELD_HITS: list[FieldHit] = _discover_field_hits()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hit", _FIELD_HITS, ids=lambda h: h.case_id)
def test_strict_request_models_field_safe(hit: FieldHit) -> None:
    """Every JSON-non-native field on a strict-mode request model MUST carry ``Field(strict=False, ...)``."""
    assert hit.has_strict_false, _format_failure(hit)


def test_walker_finds_known_baseline() -> None:
    """Defends against the vacuous-green failure mode.

    If the walker silently fails to discover any strict-mode models (e.g., a
    bug in ``_build_alias_map`` or a refactor that moved models), the
    parametrized test above degenerates to zero cases and passes silently.
    This guard asserts the 4 known baseline models are still discovered.
    """
    discovered = {cls.name for _, cls, _ in _iter_strict_request_models(_FEATURES_ROOT)}
    missing = _EXPECTED_STRICT_MODELS - discovered
    assert not missing, (
        f"Walker failed to discover expected strict-mode request models: "
        f"{sorted(missing)}. Discovered: {sorted(discovered)}. If a baseline "
        f"model was intentionally renamed or removed, update "
        f"_EXPECTED_STRICT_MODELS in this file."
    )


def test_linter_catches_synthetic_violation() -> None:
    """Negative-fixture self-test: prove the walker actually flags violations.

    Without this test, the green output of ``test_strict_request_models_field_safe``
    could be vacuous (e.g., a walker bug returning zero hits would silently pass).
    Constructs three synthetic cases (``Optional[date]``, ``datetime``, ``UUID``)
    and asserts the walker classifies each correctly.
    """
    source = textwrap.dedent(
        """
        from datetime import date, datetime
        from typing import Optional
        from uuid import UUID
        from pydantic import BaseModel, ConfigDict, Field


        class SyntheticOffender(BaseModel):
            model_config = ConfigDict(strict=True)

            opt_date: Optional[date] = None
            ts: datetime = Field(description="missing strict=False")
            uid: UUID = Field(strict=False, description="this one is fine")
        """
    )
    tree = ast.parse(source)
    aliases = _build_alias_map(tree)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))

    assert _class_has_strict_config(cls), (
        "Walker must detect ConfigDict(strict=True) on the synthetic model"
    )

    hits = list(_iter_json_non_native_fields(Path("synthetic.py"), cls, aliases))
    by_field = {h.field_name: h for h in hits}

    assert set(by_field) == {"opt_date", "ts", "uid"}, (
        f"Walker missed one or more synthetic fields. Got: {sorted(by_field)}"
    )

    assert by_field["opt_date"].resolved_type == "date"
    assert by_field["ts"].resolved_type == "datetime"
    assert by_field["uid"].resolved_type == "UUID"

    # The two violators must be flagged; the third (uid) must pass.
    assert not by_field["opt_date"].has_strict_false
    assert not by_field["ts"].has_strict_false
    assert by_field["uid"].has_strict_false

"""Unit tests for the curated SeederOverrides allow-list model (E3, #409)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.shared.seeder.overrides import SeederOverrides


class TestBounds:
    """Each knob rejects out-of-bounds values at both edges."""

    @pytest.mark.parametrize(
        ("knob", "low", "high"),
        [
            ("stores", 0, 101),
            ("products", 0, 501),
            ("window_days", 74, 366),
        ],
    )
    def test_int_knob_bounds(self, knob: str, low: int, high: int) -> None:
        with pytest.raises(ValidationError):
            SeederOverrides.model_validate({knob: low})
        with pytest.raises(ValidationError):
            SeederOverrides.model_validate({knob: high})

    @pytest.mark.parametrize(
        ("knob", "low", "high"),
        [
            ("sparsity", -0.1, 0.91),
            ("promotion_intensity", -0.1, 0.51),
            ("stockout_intensity", -0.1, 0.51),
            ("noise_sigma", -0.1, 0.51),
        ],
    )
    def test_float_knob_bounds(self, knob: str, low: float, high: float) -> None:
        with pytest.raises(ValidationError):
            SeederOverrides.model_validate({knob: low})
        with pytest.raises(ValidationError):
            SeederOverrides.model_validate({knob: high})

    def test_boundary_values_accepted(self) -> None:
        ov = SeederOverrides.model_validate(
            {
                "stores": 100,
                "products": 500,
                "window_days": 75,
                "sparsity": 0.9,
                "promotion_intensity": 0.5,
                "stockout_intensity": 0.0,
                "noise_sigma": 0.5,
            }
        )
        assert ov.stores == 100
        assert ov.window_days == 75


class TestAllowList:
    """extra='forbid' is the machine-enforced allow-list."""

    def test_unknown_knob_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SeederOverrides.model_validate({"stores": 5, "bogus_knob": 1})

    def test_strict_rejects_string_int(self) -> None:
        # strict=True: a JSON string is not coerced (validate_python path).
        with pytest.raises(ValidationError):
            SeederOverrides.model_validate({"stores": "5"})


class TestJsonPath:
    """JSON-dict validation (FastAPI's validate_python path) happy paths."""

    def test_partial_object_validates(self) -> None:
        ov = SeederOverrides.model_validate({"stores": 8, "promotion_intensity": 0.3})
        assert ov.stores == 8
        assert ov.promotion_intensity == 0.3
        assert ov.products is None

    def test_model_dump_exclude_none_is_sparse(self) -> None:
        ov = SeederOverrides.model_validate({"stores": 8, "noise_sigma": 0.25})
        assert ov.model_dump(exclude_none=True) == {"stores": 8, "noise_sigma": 0.25}


class TestIsEmpty:
    """is_empty() truth table -- {} on the wire collapses to None everywhere."""

    def test_empty_object_is_empty(self) -> None:
        assert SeederOverrides().is_empty() is True
        assert SeederOverrides.model_validate({}).is_empty() is True

    def test_any_knob_makes_non_empty(self) -> None:
        assert SeederOverrides(stores=1).is_empty() is False
        assert SeederOverrides(noise_sigma=0.0).is_empty() is False

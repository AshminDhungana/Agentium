"""Tests for effort validation on the ModelConfigCreate schema.

Locks the spec guarantee that an invalid `effort` value is rejected at the
Pydantic boundary with a 422, so a thinking param can never be requested with
an unrecognized effort level.
"""

import pytest
from pydantic import ValidationError

from backend.api.routes.models import ModelConfigCreate


def _minimal_kwargs(**overrides):
    base = dict(
        provider="OPENAI",
        config_name="test",
        default_model="gpt-4o",
    )
    base.update(overrides)
    return base


def test_invalid_effort_raises_422():
    with pytest.raises(ValidationError):
        ModelConfigCreate(**_minimal_kwargs(effort="banana"))


def test_valid_effort_passes():
    cfg = ModelConfigCreate(**_minimal_kwargs(effort="high"))
    assert cfg.effort == "high"


def test_default_effort_is_none():
    cfg = ModelConfigCreate(**_minimal_kwargs())
    assert cfg.effort == "none"

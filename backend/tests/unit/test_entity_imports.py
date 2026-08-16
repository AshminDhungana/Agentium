"""
Unit test verifying all entity models in entities/__init__.py are importable
and map to database tables (where applicable).
"""
import pytest
from backend.models import entities


def test_all_entities_in_all_are_importable():
    """Every name in entities.__all__ can be imported."""
    for name in entities.__all__:
        assert hasattr(entities, name), f"Missing export: {name}"
        model = getattr(entities, name)
        assert model is not None, f"Export {name} is None"


def test_no_duplicate_exports():
    """entities.__all__ has no duplicates."""
    assert len(entities.__all__) == len(set(entities.__all__)), "Duplicate exports in __all__"


# Table-mapped models (derived from entities.__all__ by filtering enums/base)
# Enums have __members__, Base classes are 'Base'/'BaseEntity', constants like 'AGENT_TYPE_MAP'
# Pydantic models (BaseModel subclasses) don't have __tablename__ - they're for validation, not DB tables
# Plain Python classes (like ExecutionSummary) also don't have __tablename__ - they're DTOs
# Some SQLAlchemy models inherit from Base directly, not BaseEntity (e.g., User)
# Test: verify all SQLAlchemy models have proper __tablename__
def test_table_models_have_tablename():
    """SQLAlchemy models have __tablename__ attribute."""
    from pydantic import BaseModel
    from backend.models.entities.base import Base, BaseEntity

    for name in entities.__all__:
        model = getattr(entities, name)
        is_enum = hasattr(model, '__members__')  # Enum classes have __members__
        is_base_class = name in ('Base', 'BaseEntity')
        is_constant = name == 'AGENT_TYPE_MAP'
        is_pydantic = isinstance(model, type) and issubclass(model, BaseModel)
        # SQLAlchemy models: inherit from BaseEntity OR inherit from Base but are not Base itself
        is_sqlalchemy_model = (
            isinstance(model, type) and
            (issubclass(model, BaseEntity) or (issubclass(model, Base) and model is not Base))
        )

        if is_sqlalchemy_model:
            # This is a SQLAlchemy model - must have __tablename__
            assert hasattr(model, '__tablename__'), f"{name} missing __tablename__"
            assert isinstance(model.__tablename__, str), f"{name}.__tablename__ not string"
            assert len(model.__tablename__) > 0, f"{name}.__tablename__ empty"
        elif not (is_enum or is_base_class or is_constant or is_pydantic):
            # Not a recognized type - warn but don't fail
            # (plain Python classes like ExecutionSummary fall here)
            import warnings
            warnings.warn(
                f"{name} is not a recognized type (enum, base, constant, Pydantic, or SQLAlchemy)",
                UserWarning
            )
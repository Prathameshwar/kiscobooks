import pytest
from billing_platform.db.base import Base
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from catalog import models as catalog_models
from catalog.config import Settings
from catalog.domain.field_registry import CUSTOM_ENABLED_ENTITIES, registry
from catalog.main import create_app
from tests.conftest import ACTOR_SECRET


def test_registry_only_exposes_real_native_columns() -> None:
    models = {
        mapper.class_.__name__: mapper.class_
        for mapper in Base.registry.mappers
        if mapper.class_.__module__.startswith(catalog_models.__name__ + ".")
    }
    assert registry.validate_against_models(models) == []
    assert len(CUSTOM_ENABLED_ENTITIES) == 11
    assert "catalog.unit_of_measure" not in CUSTOM_ENABLED_ENTITIES
    assert not registry.get_field("catalog.unit_of_measure", "decimal_places").hideable


def test_registry_drift_stops_startup(monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine) -> None:
    monkeypatch.setattr(registry, "validate_against_models", lambda models: ["drift"])
    with pytest.raises(RuntimeError, match="registry"):
        create_app(
            Settings(
                database_url="sqlite+aiosqlite://", actor_signing_secret=SecretStr(ACTOR_SECRET)
            ),
            engine=engine,
        )

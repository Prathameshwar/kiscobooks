"""An explicit disposable test URL must override the application's environment URL."""

from __future__ import annotations

import io

import pytest
from alembic import command

from tests.alembic_support import alembic_config


def test_migration_helper_preserves_url_escaped_characters() -> None:
    url = "mysql+asyncmy://localhost/identity_disposable_test?charset=utf8mb4&test=%20"
    assert alembic_config(url).get_main_option("sqlalchemy.url") == url


def test_explicit_migration_target_overrides_application_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IDENTITY_DATABASE_URL", "not-a-valid-application-url")
    config = alembic_config("mysql+asyncmy://localhost/identity_disposable_test")
    output = io.StringIO()
    config.output_buffer = output
    command.upgrade(config, "head", sql=True)
    assert "CREATE TABLE company_business_role" in output.getvalue()

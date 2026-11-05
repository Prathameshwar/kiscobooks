from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.import_engine import authorize_snapshot, issues


async def test_retained_template_cannot_disclose_a_newly_protected_native_column():
    old = {"schemas": {"product:CREATE": {"properties": {"name": {}, "purchase_price": {}}}}}
    adapter = SimpleNamespace(
        snapshot=AsyncMock(
            return_value={"schemas": {"product:CREATE": {"properties": {"name": {}}}}}
        )
    )
    with pytest.raises(PermissionDeniedError, match="unavailable native"):
        await authorize_snapshot(
            None, adapter, SimpleNamespace(snapshot=old, definition="products")
        )


@pytest.mark.parametrize("scope", ["x-custom-fields", "x-shared-custom-fields"])
async def test_retained_template_rechecks_each_custom_field_scope(scope):
    old = {"schemas": {"product:CREATE": {scope: [{"key": "private_note"}]}}, "parameters": {}}
    adapter = SimpleNamespace(
        snapshot=AsyncMock(return_value={"schemas": {"product:CREATE": {scope: []}}})
    )
    template = SimpleNamespace(snapshot=old, definition="products")
    with pytest.raises(PermissionDeniedError, match="unavailable custom"):
        await authorize_snapshot(None, adapter, template)
    adapter.snapshot.return_value = old
    await authorize_snapshot(None, adapter, template)


def test_configuration_issues_keep_field_paths_but_never_echo_owner_values():
    problem = ValidationFailedError(
        "secret-value",
        fields={
            "initial_setup.barcodes": "secret-value",
            "brand_id": "secret-value",
            "bad path": "secret-value",
        },
    )
    output = issues(problem)
    assert {issue["field"] for issue in output} == {"initial_setup.barcodes", "brand_id"}
    assert all(issue["code"] == "validation_failed" for issue in output)
    assert "secret-value" not in str(output)
    assert (
        len(
            issues(
                ValidationFailedError(
                    "secret", fields={str(index): "secret" for index in range(200)}
                )
            )
        )
        == 100
    )
    assert (
        issues(ValidationFailedError("secret", fields={"invalid path": "secret"}))[0]["field"] == ""
    )

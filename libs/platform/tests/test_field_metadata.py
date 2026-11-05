from dataclasses import replace
from typing import Any

import pytest

from billing_platform.authz import Scope, ScopePath
from billing_platform.custom_fields import CustomDefinition, SequenceRules, ValidationRules
from billing_platform.errors import ValidationFailedError
from billing_platform.field_metadata import (
    FieldLayout,
    ScopedDefinition,
    apply_field_access,
    changed_values,
    resolve_custom_definitions,
    resolve_layout,
)
from billing_platform.field_policy import FieldPolicyRule
from billing_platform.fields import EntityFields, NativeField
from billing_platform.ids import uuid7


def test_company_override_scope_and_logical_uniqueness() -> None:
    tenant, company = uuid7(), uuid7()
    base = CustomDefinition(
        key="cf_code",
        data_type="text",
        is_searchable=True,
        validation=ValidationRules(unique_within="tenant"),
    )
    scoped = ScopedDefinition(tenant, None, base, 1)
    override = ScopedDefinition(tenant, company, base.model_copy(update={"is_active": False}), 2)
    args: dict[str, Any] = {
        "tenant_id": tenant,
        "company_id": company,
        "native_fields": frozenset(),
        "option_sources": frozenset(),
    }
    result = resolve_custom_definitions(
        [scoped, override, replace(scoped, tenant_id=uuid7())], **args
    )
    assert len(result) == 1 and not result[0].is_active
    assert resolve_custom_definitions([replace(scoped, company_id=uuid7())], **args) == ()
    with pytest.raises(ValidationFailedError):
        resolve_custom_definitions([scoped, scoped], **args)
    with pytest.raises(ValidationFailedError):
        resolve_custom_definitions([replace(scoped, source_version=0)], **args)
    for invalid in [
        base.model_copy(update={"data_type": "integer"}),
        base.model_copy(update={"validation": ValidationRules(unique_within="company")}),
    ]:
        with pytest.raises(ValidationFailedError):
            resolve_custom_definitions([scoped, replace(override, definition=invalid)], **args)


def test_layout_and_authority_are_separate_and_company_layout_inherits() -> None:
    tenant, company = uuid7(), uuid7()
    native = EntityFields(
        "catalog.test",
        "Test",
        {
            "code": NativeField(required=True, hideable=False, reason="identity"),
            "description": NativeField(),
            "optional": NativeField(requires_feature="extra"),
        },
    )
    custom = (
        CustomDefinition(key="cf_number", data_type="auto_number", sequence_config=SequenceRules()),
    )
    layouts = [
        FieldLayout(tenant, None, "native", "description", visible=False, label="Tenant label"),
        FieldLayout(tenant, company, "native", "description", label="Company label"),
        FieldLayout(tenant, company, "native", "optional", visible=False),
    ]
    args: dict[str, Any] = {
        "tenant_id": tenant,
        "company_id": company,
        "enabled_features": frozenset(),
    }
    presentation = resolve_layout(native, custom, layouts, **args)
    description = next(field for field in presentation if field.key == "description")
    assert description.label == "Company label" and not description.visible and description.writable
    rules = [
        FieldPolicyRule("description", "read", "deny", Scope("company", company)),
        FieldPolicyRule("code", "write", "deny", Scope("company", company)),
    ]
    authorized = apply_field_access(presentation, rules=rules, target=ScopePath(company_id=company))
    assert "description" not in {field.key for field in authorized}
    assert all(not field.writable for field in authorized)
    for invalid in [
        [FieldLayout(tenant, None, "native", "code", visible=False)],
        [FieldLayout(tenant, None, "native", "unknown")],
        [layouts[0], layouts[0]],
    ]:
        with pytest.raises(ValidationFailedError):
            resolve_layout(native, custom, invalid, **args)
    assert changed_values(
        {"code": "A", "description": "x"}, {"code": "A", "description": None}
    ) == frozenset({"description"})


def test_layout_requiredness_reaches_validation_and_diff_preserves_types() -> None:
    tenant, company = uuid7(), uuid7()
    native = EntityFields("catalog.test", "Test", {})
    definition = CustomDefinition(key="cf_text", data_type="text")
    result = resolve_layout(
        native,
        (definition,),
        [FieldLayout(tenant, company, "custom", "cf_text", required=True)],
        tenant_id=tenant,
        company_id=company,
        enabled_features=frozenset(),
    )
    assert result[0].definition is not None and result[0].definition.validation.required
    assert changed_values({"value": True}, {"value": 1}) == frozenset({"value"})
    assert changed_values(
        {"children": [{"value": True}]}, {"children": [{"value": 1}]}
    ) == frozenset({"children"})
    assert not changed_values({"children": [{"value": 1}]}, {"children": [{"value": 1}]})

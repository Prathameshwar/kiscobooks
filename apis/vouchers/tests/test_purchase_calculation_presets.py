import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.tenant_context import unfiltered
from billing_platform.errors import ValidationFailedError
from conftest import COMPANY, TENANT, headers
from pydantic import ValidationError
from sqlalchemy import update
from test_foundation import create_type
from voucher_execution.invoice import InvoicePolicy

from vouchers.domain.configuration import intersect, validate_policy
from vouchers.models import core as m
from vouchers.schemas.configuration import Policy
from vouchers.schemas.purchase_calculation import (
    PurchaseCalculationPolicy,
    PurchaseCalculationPreset,
)


def recipe(**overrides):
    return {
        "key": "trade",
        "name": "Trade discount",
        "purpose": "DISCOUNT",
        "value": "10",
    } | overrides


def configured():
    return Policy.model_validate(
        {
            "invoice": {"manual_discounts_allowed": True, "charges_allowed": True},
            "purchase_calculation": {
                "presets": [
                    {
                        "key": "standard",
                        "name": "Two discounts",
                        "steps": [recipe(), recipe(key="extra", value="5")],
                    }
                ],
                "default_preset": "standard",
            },
        }
    )


def test_presets_are_typed_versioned_policy_and_do_not_change_legacy_policy_wire():
    assert "purchase_calculation" not in Policy().model_dump(mode="json")
    policy = configured()
    validate_policy("PURCHASE", "STANDARD", policy)
    assert Policy.model_validate(policy.model_dump(mode="json")) == policy
    assert policy.purchase_calculation.presets[0].steps[0].value.as_tuple().exponent == -4


@pytest.mark.parametrize(
    "step",
    [
        recipe(value="100.0001"),
        recipe(name=" "),
        recipe(value="-1"),
        recipe(expression="eval"),
        recipe(basis_recipe="AFTER_STEPS"),
        recipe(amount_basis="GROSS_INCL_TAX", tax_treatment="NO_CHANGE"),
        recipe(dependencies=["trade"]),
        recipe(key="extra", basis_recipe="AFTER_STEPS", dependencies=["unknown"]),
    ],
)
def test_invalid_or_executable_recipes_are_rejected(step):
    with pytest.raises(ValidationError):
        PurchaseCalculationPreset.model_validate({"key": "p", "name": "Preset", "steps": [step]})


def test_default_and_duplicate_identities_require_a_real_distinct_preset():
    with pytest.raises(ValidationError):
        PurchaseCalculationPolicy.model_validate({"presets": [], "default_preset": "missing"})
    with pytest.raises(ValidationError):
        PurchaseCalculationPreset.model_validate(
            {"key": "p", "name": "Preset", "steps": [recipe(), recipe()]}
        )


def test_native_policy_restricts_presets_and_other_voucher_kinds_cannot_use_them():
    with pytest.raises(ValidationFailedError, match="standard Purchase"):
        validate_policy("SALES", "STANDARD", configured())
    denied = configured().model_copy(update={"invoice": InvoicePolicy()})
    with pytest.raises(ValidationFailedError, match="enable Purchase discounts"):
        validate_policy("PURCHASE", "STANDARD", denied)


def test_class_restrictions_hide_unavailable_presets_and_clear_the_default():
    parent = configured()
    child = Policy.model_validate(
        {"schema_version": 2, "invoice": {"manual_discounts_allowed": False}}
    )
    resolved = intersect(parent, child)
    assert resolved.purchase_calculation.presets == ()
    assert resolved.purchase_calculation.default_preset is None
    inherited = intersect(parent, Policy())
    assert inherited.purchase_calculation == parent.purchase_calculation


@pytest.mark.parametrize(
    "invoice",
    [
        {"manual_discounts_allowed": True, "max_components": 1},
        {"manual_discounts_allowed": True, "max_discount_components": 1},
        {"manual_discounts_allowed": True, "allowed_scopes": ["LINE"]},
        {"manual_discounts_allowed": True, "discount_input_kinds": ["FIXED"]},
        {"manual_discounts_allowed": True, "max_discount_pct": "5"},
        {"manual_discounts_allowed": True, "discount_compounding_allowed": False},
    ],
)
def test_configured_limits_apply_to_presets(invoice):
    denied = configured().model_copy(update={"invoice": InvoicePolicy.model_validate(invoice)})
    with pytest.raises(ValidationFailedError):
        validate_policy("PURCHASE", "STANDARD", denied)


@pytest.mark.parametrize(
    "step,invoice",
    [
        (recipe(purpose="FREIGHT"), {"manual_discounts_allowed": True, "charges_allowed": False}),
        (
            recipe(input_kind="FIXED", value="10"),
            {"manual_discounts_allowed": True, "max_discount_amount": "5"},
        ),
        (
            recipe(amount_basis="GROSS_INCL_TAX"),
            {"manual_discounts_allowed": True, "discount_amount_bases": ["NET_EXCL_TAX"]},
        ),
        (
            recipe(amount_basis="GROSS_INCL_TAX"),
            {"manual_discounts_allowed": True, "allowed_price_bases": ["NET_EXCL_TAX"]},
        ),
        (recipe(), {"manual_discounts_allowed": True, "allowed_component_inputs": ["FIXED"]}),
    ],
)
def test_each_recipe_respects_charge_amount_and_basis_permissions(step, invoice):
    policy = Policy.model_validate(
        {
            "invoice": invoice,
            "purchase_calculation": {
                "presets": [{"key": "p", "name": "Purchase", "steps": [step]}]
            },
        }
    )
    with pytest.raises(ValidationFailedError):
        validate_policy("PURCHASE", "STANDARD", policy)


async def test_native_preset_revision_fieldset_scope_and_conflicts(client, prefix):
    policy = configured().model_dump(mode="json")
    kind = await create_type(client, prefix, kind="PURCHASE", policy=policy)
    path = prefix + "/voucher-types/" + kind["id"]
    selected = await client.get(
        path + "/field-set", headers=headers(), params={"date": "2026-11-02"}
    )
    assert selected.status_code == 200, selected.text
    assert (
        selected.json()["configuration"]["policy"]["purchase_calculation"]["default_preset"]
        == "standard"
    )
    replacement = configured().model_dump(mode="json")
    replacement["purchase_calculation"]["presets"][0]["steps"][1]["value"] = "4.0000"
    result = await client.post(
        path + "/revisions", headers=headers(), json={"expected_version": 1, "policy": replacement}
    )
    assert result.status_code == 200, result.text
    assert result.json()["revision_id"] != kind["revision_id"]
    stale = await client.post(
        path + "/revisions", headers=headers(), json={"expected_version": 1, "policy": policy}
    )
    assert stale.status_code == 409
    forbidden = await client.post(
        path + "/revisions",
        headers=headers(permissions=frozenset({"vouchers.read"})),
        json={"expected_version": 2, "policy": policy},
    )
    assert forbidden.status_code == 403
    foreign = uuid.uuid4()
    other = await client.get(
        path.replace(str(COMPANY), str(foreign)), headers=headers(company=foreign)
    )
    assert other.status_code == 403
    foreign_tenant = await client.get(path, headers=headers(tenant=uuid.uuid4()))
    assert foreign_tenant.status_code == 404
    invalid = await client.post(
        path + "/revisions",
        headers=headers(),
        json={
            "expected_version": 2,
            "policy": replacement | {"invoice": {"manual_discounts_allowed": False}},
        },
    )
    assert invalid.status_code == 422
    current = await client.get(path, headers=headers())
    assert current.json()["row_version"] == 2


@pytest.mark.parametrize(
    "steps,invoice",
    [
        (
            [recipe(), recipe(key="extra", name="Extra")],
            {"manual_discounts_allowed": True, "max_discount_pct": "15"},
        ),
        (
            [
                recipe(input_kind="FIXED", value="60"),
                recipe(key="extra", name="Extra", input_kind="FIXED", value="60"),
            ],
            {"manual_discounts_allowed": True, "max_discount_amount": "100"},
        ),
    ],
)
def test_discount_limits_apply_to_the_presets_total_discount(steps, invoice):
    # Accounting caps the total discount, so two steps under the limit can still exceed it.
    policy = Policy.model_validate(
        {
            "invoice": invoice,
            "purchase_calculation": {"presets": [{"key": "p", "name": "P", "steps": steps}]},
        }
    )
    with pytest.raises(ValidationFailedError, match="limit"):
        validate_policy("PURCHASE", "STANDARD", policy)
    within = policy.model_copy(
        update={
            "invoice": InvoicePolicy.model_validate(
                {
                    "manual_discounts_allowed": True,
                    "max_discount_pct": "20",
                    "max_discount_amount": "120",
                }
            )
        }
    )
    validate_policy("PURCHASE", "STANDARD", within)


def test_preset_names_must_be_distinct_for_the_bill_picker():
    with pytest.raises(ValidationError, match="names must be distinct"):
        PurchaseCalculationPolicy.model_validate(
            {
                "presets": [
                    {"key": "a", "name": "Trade terms", "steps": []},
                    {"key": "b", "name": " trade  TERMS ", "steps": []},
                ]
            }
        )


async def test_presets_only_belong_to_the_purchase_configuration_family(client, prefix):
    policy = configured().model_dump(mode="json")
    for family in ("COMMON", "SALES"):
        refused = await client.post(
            prefix + "/voucher-configurations",
            headers=headers(),
            json={"code": "P_" + family, "name": family, "family": family, "policy": policy},
        )
        assert refused.status_code == 422, refused.text
        assert "Purchase configuration family" in refused.text
    accepted = await client.post(
        prefix + "/voucher-configurations",
        headers=headers(),
        json={"code": "P_PURCHASE", "name": "Purchase", "family": "PURCHASE", "policy": policy},
    )
    assert accepted.status_code == 201, accepted.text


async def test_legacy_common_profile_with_presets_does_not_block_other_kinds(client, prefix, app):
    config = (
        await client.post(
            prefix + "/voucher-configurations",
            headers=headers(),
            json={
                "code": "LEGACY_COMMON",
                "name": "Legacy common",
                "family": "COMMON",
                "policy": {"schema_version": 2, "invoice": {"manual_discounts_allowed": True}},
            },
        )
    ).json()
    published = await client.post(
        prefix + "/voucher-configurations/" + config["id"] + "/publish",
        headers=headers(),
        json={"expected_version": 1},
    )
    assert published.status_code == 200, published.text
    bound = await client.post(
        prefix + "/voucher-configuration-bindings",
        headers=headers(),
        json={
            "expected_version": 2,
            "configuration_revision_id": config["revision_id"],
            "valid_from": "2020-01-01",
        },
    )
    assert bound.status_code == 201, bound.text
    # A profile saved before the family rule existed may already carry presets.
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            identity = uuid.UUID(config["revision_id"])
            row = await db.get(m.VoucherConfigurationRevision, identity)
            presets = configured().model_dump(mode="json")["purchase_calculation"]
            # Core update: the ORM guard rightly refuses to rewrite revision content.
            with unfiltered():
                await db.execute(
                    update(m.VoucherConfigurationRevision)
                    .where(m.VoucherConfigurationRevision.id == identity)
                    .values(policy=row.policy | {"purchase_calculation": presets})
                )
            await db.commit()
    kind = await create_type(
        client, prefix, code="LEGACY_SALES", kind="SALES", policy={"invoice": {}}
    )
    effective = await client.get(
        prefix + "/voucher-types/" + kind["id"] + "/effective-configuration",
        params={"date": "2026-11-02"},
        headers=headers(),
    )
    assert effective.status_code == 200, effective.text
    assert "purchase_calculation" not in effective.json()["policy"]

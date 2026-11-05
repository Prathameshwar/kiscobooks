import datetime as dt
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from billing_platform.errors import ValidationFailedError

from catalog.schemas.configuration import (
    EffectiveConfiguration,
    EntryOptions,
    PricingRequirements,
    ProfileDefaults,
)
from catalog.schemas.simple_products import SimpleProductCreate, SimpleProductPatch
from catalog.tasks import product_import_configuration as rules


@pytest.fixture
def config():
    return EffectiveConfiguration(
        company_id=uuid.uuid4(),
        as_of=dt.date(2026, 1, 1),
        kind="GOODS",
        policy_generation=3,
        source_version=8,
        sources=[],
        numeric_defaults=[],
        options=EntryOptions(
            **{
                **{key + "_mode": "OPTIONAL" for key in rules.OPTIONS},
                **{key + "_default": False for key in rules.OPTIONS},
            }
        ),
        profiles=ProfileDefaults(),
        pricing=PricingRequirements(),
    )


def test_template_omits_derived_guards_and_disabled_creation_fields(config):
    config.options.brand_mode = config.options.barcode_mode = config.options.model_mode = "DISABLED"
    schema = SimpleProductCreate.model_json_schema()
    type_id = str(uuid.uuid4())
    rules.template_schema(schema, config, "CREATE", {"product_type_revision_id": type_id})
    assert not rules.DERIVED.intersection(schema["properties"])
    assert "brand_id" not in schema["properties"] and "series_id" not in schema["properties"]
    assert "model_code" not in schema["properties"]
    assert "barcodes" not in schema["$defs"]["InitialProductSetup"]["properties"]
    assert schema["properties"]["product_type_revision_id"]["enum"] == [type_id]
    assert schema["properties"]["kind"]["enum"] == ["GOODS"]
    assert all(
        not rules.DERIVED.intersection(value.get("properties", {}))
        for value in schema["$defs"].values()
    )


def test_update_template_preserves_explicit_clearing_and_rejects_impossible_required_brand(config):
    config.options.brand_mode = "DISABLED"
    patch = SimpleProductPatch.model_json_schema()
    rules.template_schema(patch, config, "UPDATE", {})
    assert "brand_id" in patch["properties"] and "revision" not in patch["properties"]
    schema = SimpleProductCreate.model_json_schema()
    schema["required"].append("brand_id")
    with pytest.raises(ValidationFailedError, match="required brand"):
        rules.template_schema(schema, config, "CREATE", {})


def test_disabled_variant_and_measured_pack_options_keep_the_base_unit_available(config):
    config.options.variants_mode = "DISABLED"
    config.options.measured_units_mode = "DISABLED"
    config.options.alternate_units_mode = "DISABLED"
    schema = SimpleProductCreate.model_json_schema()
    rules.template_schema(schema, config, "CREATE", {}, simple=True)
    unit = schema["$defs"]["UnitBindingInput"]["properties"]
    assert unit["conversion_mode"]["enum"] == ["FIXED"]
    assert "BASE" in unit["role"]["enum"]
    assert not {"PACK", "MEASURED"}.intersection(unit["role"]["enum"])
    axes = [
        definition["properties"]["is_axis"]
        for definition in schema["$defs"].values()
        if "is_axis" in definition.get("properties", {})
    ]
    assert axes and all(axis["enum"] == [False] for axis in axes)


def test_guide_keeps_requiredness_separate_from_draft_creation_and_hides_variant_choice(config):
    config.options.barcode_mode = "REQUIRED"
    guide = rules.guide(config, advanced=False)
    modes = {row["key"]: row["mode"] for row in guide["options"]}
    assert modes["barcode"] == "REQUIRED" and modes["variants"] == "DISABLED"
    assert "before activation" in guide["note"]
    assert not guide["inventory_profile"]
    assert rules.guide(config, advanced=True)["options"][4]["mode"] == "OPTIONAL"


@pytest.mark.parametrize("field", ["brand", "barcode", "model"])
async def test_actual_row_rejects_disabled_options(config, monkeypatch, field):
    setattr(config.options, field + "_mode", "DISABLED")
    monkeypatch.setattr(rules, "configuration", AsyncMock(return_value=config))
    data = {"kind": "GOODS", "product_type_revision_id": str(uuid.uuid4())}
    data.update(
        {"brand_id": str(uuid.uuid4())}
        if field == "brand"
        else {"model_code": "MODEL-1"}
        if field == "model"
        else {"initial_setup": {"barcodes": [{"value": "TEST"}]}}
    )
    with pytest.raises(ValidationFailedError, match="disabled") as failure:
        await rules.creation_data(None, None, config.company_id, data)
    assert failure.value.extra["fields"]


async def test_creation_guards_are_derived_without_mutating_or_overriding_input(
    config, monkeypatch
):
    monkeypatch.setattr(rules, "configuration", AsyncMock(return_value=config))
    data = {
        "kind": "GOODS",
        "product_type_revision_id": str(uuid.uuid4()),
        "initial_setup": {
            "effective_from": "2026-01-01",
            "units": [{"code": "BASE"}, {"expected_version": 9}],
            "barcodes": [{"value": "TEST"}],
            "attributes": {"attributes": []},
        },
    }
    prepared = await rules.creation_data(None, None, config.company_id, data)
    assert "expected_generation" not in data["initial_setup"]
    setup = prepared["initial_setup"]
    assert setup["expected_generation"] == 3 and setup["expected_source_version"] == 8
    assert (
        setup["units"][0]["expected_version"]
        == setup["barcodes"][0]["expected_version"]
        == setup["attributes"]["expected_version"]
        == 1
    )
    assert setup["units"][1]["expected_version"] == 9
    assert len(setup["configuration_fingerprint"]) == 64
    assert await rules.creation_data(None, None, config.company_id, {}) == {}
    plain = {"kind": "GOODS", "product_type_revision_id": str(uuid.uuid4())}
    assert await rules.creation_data(None, None, config.company_id, plain) == plain


async def test_configuration_rejects_invalid_context_and_resolves_the_company_date(
    config, monkeypatch
):
    monkeypatch.setattr(
        rules,
        "load_field_context",
        AsyncMock(return_value=SimpleNamespace(company=SimpleNamespace(timezone="Asia/Kolkata"))),
    )
    resolver = AsyncMock(return_value=config)
    monkeypatch.setattr(rules, "resolve", resolver)
    assert await rules.configuration(None, None, config.company_id, {"kind": "GOODS"}) == config
    assert isinstance(resolver.call_args.args[3].as_of, dt.date)
    with pytest.raises(ValidationFailedError, match="valid product"):
        await rules.configuration(None, None, config.company_id, {"kind": "INVALID"})


@pytest.mark.parametrize("simple", [False, True])
async def test_disabled_update_preserves_saved_brand_and_allows_explicit_clearing(
    config, monkeypatch, simple
):
    config.options.brand_mode = "DISABLED"
    old = uuid.uuid4()
    family = SimpleNamespace(id=uuid.uuid4(), kind="GOODS", brand_id=old, series_id=None)
    item = SimpleNamespace(id=uuid.uuid4(), family_id=family.id)
    getter = AsyncMock(side_effect=[item, family] if simple else [family])
    monkeypatch.setattr(rules, "company_object", getter)
    monkeypatch.setattr(rules, "configuration", AsyncMock(return_value=config))
    resource = "simple_product" if simple else "product_family"
    await rules.update_options(
        None, None, config.company_id, resource, uuid.uuid4(), {"brand_id": None}
    )
    getter.assert_not_called()
    await rules.update_options(
        None, None, config.company_id, resource, uuid.uuid4(), {"brand_id": old}
    )
    getter.side_effect = [item, family] if simple else [family]
    with pytest.raises(ValidationFailedError, match="disabled"):
        await rules.update_options(
            None, None, config.company_id, resource, uuid.uuid4(), {"brand_id": uuid.uuid4()}
        )

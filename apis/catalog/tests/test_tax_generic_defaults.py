"""Generic choices require an explicit policy scope, never a missing applicability bypass."""

import uuid
from decimal import Decimal
from importlib.resources import files

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.projections import CompanyProjection
from catalog.models.tax import CatalogTaxBinding, TaxRate, TaxRule
from catalog.models.tax_governance import TaxRuleApplicability
from catalog.schemas.tax import RuleInput
from catalog.schemas.tax_defaults import TaxStarterPack
from catalog.tasks import tax_defaults
from catalog.tasks.tax_defaults import ensure_tax_defaults, starter_pack
from tests.product_review_factories import changed
from tests.tax_factories import query, seed_tax
from tests.test_tax_defaults import provision

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def test_starter_has_generic_current_rates_and_distinct_untaxed_treatments() -> None:
    pack = starter_pack()
    assert pack.version == "IN_GST_STARTER_2"
    expected = {
        "GOODS": {Decimal(value) for value in ("0.1", "0.25", "1.5", "3", "5", "12", "18", "40")},
        "SERVICE": {Decimal(value) for value in ("1.5", "5", "7.5", "12", "18", "40")},
    }
    for kind, percentages in expected.items():
        rules = [rule for rule in pack.rules if rule.item_kind == kind]
        assert {r.percentage for r in rules if r.treatment == "TAXABLE"} == percentages
        assert {r.treatment for r in rules} == {"TAXABLE", "NIL_RATED", "EXEMPT", "NON_GST"}
        assert all(r.classification_scope == "ANY" and not r.classifications for r in rules)
        assert all(
            not any(
                word in r.name.lower()
                for word in ("milk", "dairy", "conditioner", "tea", "computer")
            )
            for r in rules
        )
        assert not any("zero-rated" in r.name.lower() for r in rules)


async def test_generic_scope_is_explicit_and_specific_empty_still_blocks(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await db.execute(
                delete(TaxRuleApplicability).where(TaxRuleApplicability.rule_id == ids["tax_rule"])
            )
    blocked = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["missing"] == ["rule_applicability"]
    async with changed(factory, tenant_a, TaxRule, ids["tax_rule"], classification_scope="ANY"):
        resolved = await client.post(
            root + "/tax-configurations/resolve", headers=auth, json=query(ids)
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "COMPLETE"
        assert resolved.json()["classification_id"] is not None
        async with changed(
            factory,
            tenant_a,
            CatalogTaxBinding,
            ids["binding_SALE_CLASSIFICATION"],
            mode="REQUIRE_EXPLICIT",
            classification_id=None,
        ):
            missing = await client.post(
                root + "/tax-configurations/resolve", headers=auth, json=query(ids)
            )
            assert missing.status_code == 200 and missing.json()["status"] == "REQUIRE_EXPLICIT"


async def test_legacy_names_upgrade_without_changing_rates_or_user_edits(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    from billing_platform.ids import uuid7

    company = uuid7()
    await provision(factory, tenant_a, company)
    legacy = TaxStarterPack.model_validate_json(
        files("catalog.seeds").joinpath("tax_defaults_v1.json").read_text(encoding="utf-8")
    )
    current = starter_pack()
    monkeypatch.setattr(tax_defaults, "starter_pack", lambda: legacy)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await ensure_tax_defaults(db, company)
            edited = await db.scalar(select(TaxRule).where(TaxRule.code == "GST1_8471"))
            assert edited is not None
            edited.name, edited.row_version = "My custom label", 2
            legacy_rule = await db.scalar(select(TaxRule).where(TaxRule.code == "GST1_0402"))
            assert legacy_rule is not None
            rule_id = legacy_rule.id
            before = {
                (r.id, r.series_id, r.valid_from, r.valid_to)
                for r in await db.scalars(select(TaxRate))
            }
        monkeypatch.setattr(tax_defaults, "starter_pack", lambda: current)
        async with factory.begin() as db:
            result = await ensure_tax_defaults(db, company)
            assert result.rules_created == 20
            legacy_rule = await db.get(TaxRule, rule_id)
            assert legacy_rule is not None and legacy_rule.name == "GST 5% - HSN 0402"
            assert legacy_rule.classification_scope == "SPECIFIC" and legacy_rule.row_version == 2
            edited = await db.scalar(select(TaxRule).where(TaxRule.code == "GST1_8471"))
            assert (
                edited is not None and edited.name == "My custom label" and edited.row_version == 2
            )
            after = {
                (r.id, r.series_id, r.valid_from, r.valid_to)
                for r in await db.scalars(select(TaxRate))
            }
            assert before <= after


def test_generic_scope_rejects_mixed_or_unknown_applicability() -> None:
    from pydantic import ValidationError

    from tests.tax_factories import EVIDENCE

    body = dict(
        code="TEST",
        name="Test",
        item_kind="GOODS",
        treatment="TAXABLE",
        tax_category_id=uuid.uuid4(),
        **EVIDENCE,
    )
    assert RuleInput.model_validate(body).classification_scope == "SPECIFIC"
    assert RuleInput.model_validate(dict(body, classification_scope="ANY")).classifications == []
    for extra in (
        {"classification_scope": "UNKNOWN"},
        {
            "classification_scope": "ANY",
            "classifications": [{"code_system": "HSN", "code": "1234"}],
        },
    ):
        with pytest.raises(ValidationError):
            RuleInput.model_validate(dict(body, **extra))


@pytest.mark.parametrize(
    "code,treatment,total",
    [
        ("GST_G_40", "TAXABLE", "40"),
        ("GST_G_NIL", "NIL_RATED", "0"),
        ("GST_G_EXEMPT", "EXEMPT", None),
        ("GST_G_NON_GST", "NON_GST", None),
    ],
)
async def test_prepared_generic_choices_resolve_with_explicit_classification_and_treatment(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    code: str,
    treatment: str,
    total: str | None,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a, treatment=treatment)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            profile = await db.scalar(
                select(CompanyProjection).where(CompanyProjection.company_id == company)
            )
            assert profile is not None
            profile.default_tax_system = "gst_in"
            await ensure_tax_defaults(db, company)
            rule = await db.scalar(
                select(TaxRule).where(TaxRule.company_id == company, TaxRule.code == code)
            )
            assert rule is not None
            for direction in ("SALE", "PURCHASE"):
                binding = await db.get(CatalogTaxBinding, ids[f"binding_{direction}_RULE"])
                category = await db.get(CatalogTaxBinding, ids[f"binding_{direction}_TREATMENT"])
                assert binding is not None and category is not None
                binding.rule_id, category.tax_category_id = rule.id, rule.tax_category_id
    response = await client.post(
        root + "/tax-configurations/resolve", headers=auth, json=query(ids)
    )
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["status"] == "COMPLETE" and value["treatment"] == treatment
    assert value["classification_code"] == "1234"
    if total is None:
        assert value["rates"] == [] and value["exemption_reason"]
    else:
        assert len(value["rates"]) == 3
        for rate in value["rates"]:
            assert sum(Decimal(part["percentage"]) for part in rate["components"]) == Decimal(total)


async def test_classification_scope_respects_native_field_permissions(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from tests.test_master_reference_policy import policy

    root, auth, ids = await seed_tax(factory, tenant_a)
    await policy(
        factory,
        tenant_a,
        uuid.UUID(root.rsplit("/", 1)[1]),
        ids["actor_user"],
        "catalog.tax_rule",
        "classification_scope",
        "read",
        version=3,
    )
    detail = await client.get(root + "/tax-rules/" + str(ids["tax_rule"]), headers=auth)
    assert detail.status_code == 200 and "classification_scope" not in detail.json()
    resolved = await client.post(
        root + "/tax-configurations/resolve", headers=auth, json=query(ids)
    )
    assert resolved.status_code == 403, resolved.text


async def test_generic_rule_authoring_rejects_later_specific_restrictions(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from tests.pricing_factories import create
    from tests.tax_factories import EVIDENCE
    from tests.test_commercial_api import command_headers

    root, auth, ids = await seed_tax(factory, tenant_a)
    created = await create(
        client,
        root,
        auth,
        "/tax-rules",
        {
            "code": "GENERIC",
            "name": "Generic test template",
            "item_kind": "GOODS",
            "treatment": "EXEMPT",
            "classification_scope": "ANY",
            "tax_category_id": str(ids["tax_category"]),
            **EVIDENCE,
        },
    )
    detail = await client.get(root + "/tax-rules/" + created["id"], headers=auth)
    assert detail.json()["classification_scope"] == "ANY"
    restricted = await client.post(
        root + "/tax-rule-applicabilities",
        headers=command_headers(auth),
        json={"rule_id": created["id"], "code_system": "HSN", "code": "1234"},
    )
    assert restricted.status_code == 422 and "generic" in restricted.text, restricted.text

"""Review cases for future commercial evidence, exact bounds and authority."""

import datetime as dt
import uuid
from decimal import Decimal
from fractions import Fraction

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import ItemUnitBinding, ItemUnitRevision, ProductPricingPolicy
from catalog.models import pricing as m
from catalog.schemas.pricing import DraftInput
from catalog.tasks import pricing_commands, pricing_schedule
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_readiness import assess
from catalog.tasks.pricing_schedule import first_gap
from tests.pricing_factories import create, pack_unit
from tests.pricing_storage_factories import seed_pricing
from tests.test_api import headers
from tests.test_master_reference_policy import policy
from tests.test_pricing_defensive_storage import actor
from tests.test_pricing_readiness import draft_body
from tests.test_pricing_resolution import query
from tests.test_pricing_schedule_readiness import preview

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")
DATE = dt.date(2090, 1, 1)


@pytest.mark.parametrize("kind", ["guard", "formula", "unit", "permission", "past"])
async def test_declared_future_dependencies_are_reviewed_with_current_authority(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    root = f"/v1/companies/{company}"
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    setup = {
        "series": {"id": str(ids["item_price_series"])},
        "numeric": {"id": str(ids["item_price_numeric_revision"])},
    }
    body = draft_body(setup)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            rule = await db.get(m.CommercialGuardRule, ids["commercial_guard_rule"])
            cost = await db.get(m.ItemReferenceCost, ids["item_reference_cost"])
            revision = await db.get(ItemUnitRevision, ids["item_unit_revision"])
            assert rule is not None and cost is not None and revision is not None
            if kind in {"guard", "permission"}:
                rule.valid_from, rule.amount = dt.date(2091, 1, 1), Decimal(110)
                if kind == "permission":
                    rule.rule_kind, rule.amount = "MIN_MARKUP", None
                    rule.percentage, rule.estimate_kind = Decimal(25), "STANDARD_ESTIMATE"
            elif kind == "formula":
                cost.valid_to = dt.date(2090, 1, 31)
                db.add(
                    m.ItemReferenceCost(
                        tenant_id=tenant_a,
                        company_id=company,
                        item_id=ids["item"],
                        unit_revision_id=revision.id,
                        numeric_revision_id=cost.numeric_revision_id,
                        currency="INR",
                        estimate_kind="STANDARD_ESTIMATE",
                        amount=Decimal(24),
                        price_basis_quantity=Decimal(1),
                        tax_basis="EXCLUSIVE",
                        source_reference="Synthetic future estimate",
                        valid_from=dt.date(2090, 2, 1),
                    )
                )
                body.update(
                    price_method="FORMULA",
                    amount=None,
                    formula={
                        "recipe": "REFERENCE_COST_PLUS_MARKUP",
                        "percentage": "25",
                        "estimate_kind": "STANDARD_ESTIMATE",
                        "rounding_mode": "HALF_UP",
                    },
                )
            elif kind == "unit":
                revision.valid_to = dt.date(2090, 12, 31)
    draft = await create(client, root, auth, "/price-drafts", body)
    if kind == "permission":
        await policy(
            factory,
            tenant_a,
            company,
            ids["actor_user"],
            "catalog.item_reference_cost",
            "amount",
            "read",
        )
        denied = await client.get(root + "/price-drafts/" + draft["id"] + "/preview", headers=auth)
        assert denied.status_code == 403, denied.text
        return
    if kind == "past":
        monkeypatch.setattr(
            pricing_commands, "utcnow", lambda: dt.datetime(2090, 1, 2, tzinfo=dt.UTC)
        )
    result = await preview(client, root, auth, draft)
    assert result["publishable"] is False, result
    if kind == "past":
        assert result["valid"] and result["publication_issues"][0]["code"] == "PAST_PUBLICATION"
    elif kind == "unit":
        assert result["coverage_valid_to"] == "2090-12-31"
        assert result["issues"][0]["code"] == "UNIT_COVERAGE_GAP"
    else:
        assert result["valid"] is False
        assert {
            "code": "BELOW_MINIMUM",
            "as_of": "2091-01-01" if kind == "guard" else "2090-02-01",
            "message": "regular price is below an applicable minimum",
        } in result["issues"]


async def test_inclusive_mrp_blocks_even_when_another_guard_needs_tax(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    root = f"/v1/companies/{company}"
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            plan = await db.get(m.PricePlan, ids["price_plan"])
            mrp = await db.get(m.ItemMrp, ids["item_mrp"])
            assert plan is not None and mrp is not None
            plan.tax_basis, mrp.amount = "INCLUSIVE", Decimal(90)
    draft = await create(
        client,
        root,
        auth,
        "/price-drafts",
        draft_body(
            {
                "series": {"id": str(ids["item_price_series"])},
                "numeric": {"id": str(ids["item_price_numeric_revision"])},
            }
        ),
    )
    result = await preview(client, root, auth, draft)
    assert result["valid"] is False and result["issues"][0]["code"] == "ABOVE_MAXIMUM"
    resolved = await client.post(root + "/prices/resolve", headers=auth, json=query(ids))
    assert resolved.status_code == 409, resolved.text


def test_coverage_interval_edges() -> None:
    end = dt.date(2090, 1, 31)
    following = dt.date(2090, 2, 1)
    assert first_gap([], DATE, None) == DATE
    assert first_gap([(DATE, end)], DATE, None) == following
    assert first_gap([(DATE, end)], DATE, end) is None
    assert first_gap([(DATE, end), (following, None)], DATE, None) is None
    assert first_gap([(DATE, end), (dt.date(2090, 2, 2), None)], DATE, None) == following
    assert first_gap([(DATE, dt.date.max)], DATE, None) is None
    with pytest.raises(ConflictError, match="ambiguous"):
        first_gap([(DATE, end), (end, None)], DATE, None)


async def test_derived_price_coverage_uses_the_requested_pack_mrp(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    current = actor(tenant_a, company, ids["actor_user"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            master = await pack_unit(db, tenant_a, company)
            pack = ItemUnitBinding(
                tenant_id=tenant_a,
                company_id=company,
                item_id=ids["item"],
                unit_id=master.id,
                code="CASE",
                usage_role="PACK",
            )
            db.add(pack)
            await db.flush()
            revision = ItemUnitRevision(
                tenant_id=tenant_a,
                company_id=company,
                binding_id=pack.id,
                revision=1,
                conversion_mode="FIXED",
                numerator=12,
                denominator=1,
                quantity_decimal_places=0,
                quantity_increment=Decimal(1),
                fractional_entry=False,
                valid_from=DATE,
            )
            db.add(revision)
            await db.flush()
            numeric = m.ItemPriceNumericRevision(
                tenant_id=tenant_a,
                company_id=company,
                item_id=ids["item"],
                unit_revision_id=revision.id,
                currency="INR",
                price_decimal_places=4,
                valid_from=DATE,
            )
            db.add(numeric)
            await db.flush()
            pricing = await db.get(ProductPricingPolicy, ids["product_pricing_policy"])
            assert pricing is not None
            pricing.mrp_mode = "REQUIRED"
            declaration = m.ItemMrp(
                tenant_id=tenant_a,
                company_id=company,
                item_id=ids["item"],
                unit_revision_id=revision.id,
                numeric_revision_id=numeric.id,
                currency="INR",
                jurisdiction="IN",
                tax_basis="INCLUSIVE",
                amount=Decimal(1440),
                price_basis_quantity=Decimal(1),
                source_reference="Synthetic pack declaration",
                valid_from=DATE,
                valid_to=dt.date(2090, 1, 31),
            )
            db.add(declaration)
            await db.flush()
            body = DraftInput.model_validate(
                draft_body(
                    {
                        "series": {"id": str(ids["item_price_series"])},
                        "numeric": {"id": str(ids["item_price_numeric_revision"])},
                    }
                )
            )
            result = await assess(
                ConfigurationAccess(db, current, company),
                body,
                entering=False,
                requested_revision=revision.id,
                unit_factor=Fraction(12),
                check_schedule=True,
            )
            assert result.coverage_valid_to == dt.date(2090, 1, 31)
            assert any(issue.code == "SOURCE_COVERAGE_GAP" for issue in result.issues)
            assert declaration.id in result.source_ids


@pytest.mark.parametrize("kind", ["rows", "dates", "overlap", "free_sale"])
async def test_schedule_limits_ambiguity_and_future_free_sale_revocation(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    current = actor(tenant_a, company, ids["actor_user"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            commercial = await db.get(m.ItemCommercialPolicy, ids["item_commercial_policy"])
            assert commercial is not None
            if kind == "rows":
                monkeypatch.setattr(pricing_schedule, "MAX_HISTORY_ROWS", 0)
            else:
                commercial.valid_to = None if kind == "overlap" else dt.date(2090, 1, 31)
                db.add(
                    m.ItemCommercialPolicy(
                        tenant_id=tenant_a,
                        company_id=company,
                        item_id=ids["item"],
                        valid_from=dt.date(2090, 2, 1),
                        free_sale_allowed=False,
                    )
                )
                if kind == "dates":
                    monkeypatch.setattr(pricing_schedule, "MAX_REVIEW_DATES", 0)
            if kind == "free_sale":
                commercial.free_sale_allowed = True
                rule = await db.get(m.CommercialGuardRule, ids["commercial_guard_rule"])
                assert rule is not None
                rule.severity = "REQUIRE_APPROVAL"
            await db.flush()
            body = DraftInput.model_validate(
                draft_body(
                    {
                        "series": {"id": str(ids["item_price_series"])},
                        "numeric": {"id": str(ids["item_price_numeric_revision"])},
                    },
                    amount="0" if kind == "free_sale" else "100",
                )
            )
            access = ConfigurationAccess(db, current, company)
            if kind == "free_sale":
                result = await assess(access, body, check_schedule=True)
                assert [(issue.code, issue.as_of) for issue in result.issues] == [
                    ("FUTURE_DEFINITION_INVALID", dt.date(2090, 2, 1))
                ]
                with pytest.raises(ConflictError):
                    result.require_valid()
            else:
                with pytest.raises(
                    ConflictError,
                    match={"rows": "review bound", "dates": "review dates", "overlap": "ambiguous"}[
                        kind
                    ],
                ):
                    await assess(access, body, check_schedule=True)

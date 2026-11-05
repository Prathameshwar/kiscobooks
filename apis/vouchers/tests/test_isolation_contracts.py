import datetime as dt
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from sqlalchemy import select

from vouchers.domain.configuration import intersect, validate_policy
from vouchers.domain.registry import BY_KIND, KINDS
from vouchers.events.execution import ExecutionResult
from vouchers.metadata import service_metadata
from vouchers.models import core as m
from vouchers.models import invoice as invoice_models
from vouchers.schemas.configuration import Policy
from vouchers.tasks.operations import apply_result

# Platform tables owned by billing_platform (idempotency, outbox, consumer dedupe). They have no
# company scope and are isolated by the platform library's own tests, not by this graph.
PLATFORM_TABLES = frozenset({"idempotency_key", "outbox", "processed_message"})


def company_tables():
    """Every service table that carries tenant and company scope, whatever its name."""
    return [
        table for table in service_metadata().sorted_tables if table.name not in PLATFORM_TABLES
    ]


def test_every_service_table_is_company_scoped_or_a_named_platform_table():
    """A new table without tenant/company columns must be named here, never silently skipped."""
    scoped = {"tenant_id", "company_id"}
    assert all(scoped <= set(table.c.keys()) for table in company_tables())
    assert PLATFORM_TABLES <= {table.name for table in service_metadata().sorted_tables}


async def seed_graph(factory, tenant, company):
    rows = {}
    model_map = {mapper.local_table.name: mapper.class_ for mapper in m.Base.registry.mappers}
    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            for table in company_tables():
                values = {"id": uuid7(), "tenant_id": tenant, "company_id": company}
                for column in table.columns:
                    if column.name in values or column.nullable or column.default:
                        continue
                    kind = type(column.type).__name__
                    values[column.name] = (
                        uuid7()
                        if kind == "Uuid7"
                        else dt.datetime.now(dt.UTC)
                        if kind == "UtcDateTime"
                        else dt.date.today()
                        if kind == "Date"
                        else Decimal("1")
                        if kind in {"Quantity", "Money", "Numeric"}
                        else {}
                        if kind == "JSON"
                        else 1
                        if kind in {"Integer", "BigInteger"}
                        else True
                        if kind == "Boolean"
                        else "a" * min(getattr(column.type, "length", None) or 1, 64)
                    )
                for constraint in table.foreign_key_constraints:
                    parent = rows[constraint.referred_table.name]
                    for element in constraint.elements:
                        values[element.parent.name] = getattr(parent, element.column.name)
                if table.name == "voucher_account_detail":
                    values["side"] = "DEBIT"
                if table.name == "voucher_bill_instruction":
                    values["debt_item_id"] = uuid7()
                    values["credit_item_id"] = uuid7()
                if table.name == "voucher_invoice_detail":
                    values["date_contract_version"] = 2
                if table.name == "voucher_item_regulatory_projection":
                    values.update(
                        product_kind="NON_DRUG",
                        licence_class=None,
                        prescription_schedule=None,
                    )
                if table.name == "voucher_party_drug_licence_projection":
                    values["licence_form"] = "20B"
                if table.name == "voucher_fulfillment_terms":
                    values["purpose"] = "PROCURE"
                # Tables with CHECK-constrained columns need a member of the permitted set (a
                # placeholder string would be refused by the database, exercising nothing).
                if table.name == "voucher_stock_context":
                    values["action"] = "RECEIPT"
                if table.name == "voucher_print_job":
                    values["status"] = "PENDING"
                if table.name == "stock_opening_import":
                    values["state"] = "STAGED"
                if table.name == "stock_retirement_fence":
                    # A closed lease, so it does not fence the stock rows seeded after it.
                    now = dt.datetime.now(dt.UTC)
                    values.update(expires_at=now + dt.timedelta(hours=1), closed_at=now)
                if table.name == "counter_operator":
                    values["status"] = "ACTIVE"
                if table.name == "counter_cash_event":
                    values["direction"] = "IN"
                if table.name == "voucher_assignment":
                    values["role"] = "SELLER"
                if table.name == "counter_session":
                    values["status"] = "OPEN"
                if table.name == "voucher_supply_tax_context":
                    values.update(date_contract_version=2, profile="UNTAXED_ACCOUNT")
                if table.name == "voucher_supply_detail":
                    values["supply_kind"] = "SERVICE"
                    values["price_basis"] = "NET_EXCL_TAX"
                if table.name == "voucher_supply_quantity":
                    values["basis"] = "BILLED"
                if table.name == "voucher_charge_detail":
                    values.update(
                        scope="LINE", effect="DEDUCT", input_kind="PERCENT", percentage=Decimal(1)
                    )
                if table.name == "voucher_charge_target":
                    values["purpose"] = "BASIS"
                if table.name == "voucher_import_job":
                    values.update(kind="PURCHASE", source_format="CSV")
                if table.name == "voucher_import_artifact":
                    values["content"] = b"x"
                if table.name == "voucher_charge_dependency":
                    original_line = rows["voucher_line"]
                    extra_line = m.VoucherLine(
                        **{
                            column.name: getattr(original_line, column.name)
                            for column in m.VoucherLine.__table__.columns
                        }
                        | {
                            "id": uuid7(),
                            "line_key": uuid7(),
                            "sequence": original_line.sequence + 1,
                        }
                    )
                    db.add(extra_line)
                    await db.flush()
                    original_charge = rows["voucher_charge_detail"]
                    extra_charge = invoice_models.VoucherChargeDetail(
                        **{
                            column.name: getattr(original_charge, column.name)
                            for column in invoice_models.VoucherChargeDetail.__table__.columns
                        }
                        | {
                            "id": uuid7(),
                            "line_id": extra_line.id,
                            "sequence": original_charge.sequence + 1,
                        }
                    )
                    db.add(extra_charge)
                    await db.flush()
                    values["depends_on_id"] = extra_charge.id
                row = model_map[table.name](**values)
                db.add(row)
                await db.flush()
                rows[table.name] = row
    return rows


async def test_every_new_table_is_tenant_filtered(app):
    first, second = uuid7(), uuid7()
    a = await seed_graph(app.state.session_factory, first, uuid7())
    b = await seed_graph(app.state.session_factory, second, uuid7())
    # Both tenants' graphs must cover every company-scoped table: a skipped table proves nothing.
    assert set(a) == set(b) == {table.name for table in company_tables()}
    with tenant_scope(first):
        async with app.state.session_factory() as db:
            for name, row in a.items():
                model = type(row)
                found = list(await db.scalars(select(model)))
                assert row.id in {item.id for item in found}, name
                assert all(
                    item.tenant_id == first and item.company_id == row.company_id for item in found
                ), name
                assert await db.get(model, b[name].id) is None, name


def test_catalogue_and_required_profiles_match_plan():
    import re
    from pathlib import Path

    doc = Path(__file__).resolve().parents[3] / "docs/vouchers-plan.md"
    documented = set(re.findall(r"^\| `([A-Z_]+)` \|", doc.read_text(encoding="utf-8"), re.M))
    assert set(BY_KIND) == documented
    assert "QUOTATION" in BY_KIND["SALES_ORDER"].profiles
    assert "PRO_FORMA" in BY_KIND["SALES"].profiles
    assert "REQUISITION" in BY_KIND["STOCK_JOURNAL"].profiles
    assert "DELIVERY_CHALLAN" in BY_KIND["DELIVERY_NOTE"].profiles


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_has_a_bounded_foundation_policy(kind):
    validate_policy(kind.code, kind.profiles[0], Policy())
    with pytest.raises(ValidationFailedError):
        validate_policy(kind.code, "UNKNOWN", Policy())


def test_policy_cannot_widen_parent():
    parent = Policy(
        max_lines=2,
        narration_required=True,
        allowed_modes=frozenset({"ACCOUNTS"}),
        header_field_keys=frozenset({"cf_one"}),
    )
    child = Policy(max_lines=200, header_field_keys=frozenset({"cf_one", "cf_two"}))
    effective = intersect(parent, child)
    assert effective.max_lines == 2 and effective.narration_required
    assert effective.allowed_modes == {"ACCOUNTS"} and effective.header_field_keys == {"cf_one"}
    with pytest.raises(ValidationFailedError):
        intersect(parent, Policy(allowed_modes=frozenset({"ITEMS"}), default_mode="ITEMS"))


async def test_execution_identity_and_terminal_cancel_fence(app):
    tenant, company = uuid7(), uuid7()
    graph = await seed_graph(app.state.session_factory, tenant, company)
    with tenant_scope(tenant):
        async with app.state.session_factory() as db, db.begin():
            row = await db.get(m.VoucherOperation, graph["voucher_operation"].id)
            row.status = "PENDING"
            result = ExecutionResult(
                tenant_id=tenant,
                company_id=company,
                operation_id=row.id,
                execution_id=row.execution_id,
                content_hash=row.content_hash,
                configuration_hash=row.configuration_hash,
                request_hash=row.request_hash,
                outcome="CANCELLED",
            )
            await apply_result(db, result)
            await db.flush()
            assert (await apply_result(db, result)).status == "CANCELLED"
            with pytest.raises(ConflictError):
                await apply_result(
                    db,
                    result.model_copy(
                        update={"outcome": "REJECTED", "rejection_code": "CLOSED_PERIOD"}
                    ),
                )
            with pytest.raises(ConflictError):
                await apply_result(db, result.model_copy(update={"content_hash": "d" * 64}))


async def test_content_revisions_cannot_be_rewritten_directly(app):
    tenant, company = uuid7(), uuid7()
    graph = await seed_graph(app.state.session_factory, tenant, company)
    with tenant_scope(tenant):
        async with app.state.session_factory() as db:
            revision = await db.get(m.VoucherRevision, graph["voucher_revision"].id)
            revision.narration = "rewritten history"
            with pytest.raises(ConflictError):
                await db.flush()

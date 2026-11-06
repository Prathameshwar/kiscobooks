"""Signed owner preview, live user authority and no monetary side effects."""

import secrets
import uuid
from decimal import Decimal

import httpx
import pytest
from billing_platform.company_context import sign_company_context, verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.owner_snapshot import SnapshotCredential
from billing_platform.service_auth import CompanyServiceScope
from pydantic import SecretStr
from sqlalchemy import func, select
from voucher_execution.contracts import DelegatedAuthority
from voucher_execution.invoice import InvoicePreviewCommand, InvoiceQuantity
from voucher_execution.transport import ExecutionClient

from accounting.models.ledger import Journal
from accounting.models.masters import Account
from tests.conftest import COMPANY, SECRET, TENANT, USER
from tests.test_ledger_api import LEDGER_PERMISSIONS, journal_setup, ledger_headers
from tests.test_openings_sources import party_accounts


def authority(**kwargs):
    headers = ledger_headers(permissions=LEDGER_PERMISSIONS | {"vouchers.read"}, **kwargs)
    company = verify_company_context(
        headers["X-Company-Context"], headers["X-Company-Signature"], SECRET.encode()
    )
    encoded, signature = sign_company_context(
        company.model_copy(update={"policy_namespaces": frozenset({"accounting", "vouchers"})}),
        SECRET.encode(),
    )
    return DelegatedAuthority(
        actor_context=headers["X-Actor-Context"],
        actor_signature=headers["X-Actor-Signature"],
        company_context=encoded,
        company_signature=signature,
    ), company


async def setup(client, app):
    await journal_setup(client, app)
    _, customer, supplier = await party_accounts(client)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            account = await db.scalar(select(Account).where(Account.code == "SALES_REVENUE"))
            offset = str(account.id)
            version = account.row_version
    delegated, company = authority()
    line = str(uuid7())
    command = InvoicePreviewCommand.model_validate(
        {
            "tenant_id": TENANT,
            "company_id": COMPANY,
            "actor_user_id": USER,
            "authority": delegated,
            "kind": "SALES",
            "currency": "INR",
            "document_date": "2026-04-02",
            "posting_date": "2026-04-02",
            "configuration_hash": "a" * 64,
            "company_configuration_hash": company.finance.configuration_hash,
            "policy": {"manual_discounts_allowed": True},
            "invoice": {
                "party_line_key": uuid7(),
                "party_account_id": customer["id"],
                "party_account_version": customer["row_version"],
                "bill_reference": "SERVICE-1",
                "due_date": "2026-04-30",
                "tax": {"profile": "UNTAXED_ACCOUNT"},
                "supplies": [
                    {
                        "line_key": line,
                        "account_id": offset,
                        "account_version": version,
                        "supply_kind": "SERVICE",
                        "description": "Advisory service",
                        "amount": "1000",
                    }
                ],
                "components": [
                    {
                        "component_key": uuid7(),
                        "purpose": "DISCOUNT",
                        "scope": "LINE",
                        "effect": "DEDUCT",
                        "input_kind": "PERCENT",
                        "value": "10",
                        "targets": [line],
                        "source_evidence": "Approved trade terms",
                    }
                ],
            },
        }
    )
    return command, connection(client, app), supplier


def connection(client, app):
    key, secret = "invoice.preview", SecretStr(secrets.token_hex(32))
    app.state.settings.voucher_execution_credentials[key] = SnapshotCredential(
        secret=secret, scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),)
    )
    return ExecutionClient(client, "http://127.0.0.1", key, secret.get_secret_value().encode())


async def test_signed_preview_is_stable_and_does_not_post(client, app):
    command, transport, supplier = await setup(client, app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            before = await db.scalar(select(func.count(Journal.id)))
    try:
        result = await transport.preview(command)
    except httpx.HTTPStatusError as error:
        pytest.fail(error.response.text)
    assert result.payable == 900 and result.tax_total == 0
    assert await transport.preview(command) == result
    accepted = command.model_copy(
        update={
            "invoice": command.invoice.model_copy(
                update={"accepted_calculation_hash": result.calculation_hash}
            )
        }
    )
    assert await transport.preview(accepted) == result
    accepted_with_payable = command.model_copy(
        update={
            "invoice": command.invoice.model_copy(
                update={
                    "accepted_calculation_hash": result.calculation_hash,
                    "payable_total": result.payable,
                }
            )
        }
    )
    assert await transport.preview(accepted_with_payable) == result
    changed = command.model_copy(
        update={"invoice": command.invoice.model_copy(update={"components": ()})}
    )
    assert (await transport.preview(changed)).calculation_hash != result.calculation_hash
    stale = command.model_copy(
        update={"invoice": command.invoice.model_copy(update={"party_account_version": 999})}
    )
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(stale)
    assert error.value.response.status_code == 409
    wrong_role = command.model_copy(
        update={
            "invoice": command.invoice.model_copy(
                update={
                    "party_account_id": uuid.UUID(supplier["id"]),
                    "party_account_version": supplier["row_version"],
                }
            )
        }
    )
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(wrong_role)
    assert error.value.response.status_code == 422
    wrong_scope = command.model_copy(update={"company_id": uuid7()})
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(wrong_scope)
    assert error.value.response.status_code == 401
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(Journal.id))) == before


async def test_sales_noncredit_policy_requires_exact_settlement(client, app):
    command, transport, _ = await setup(client, app)
    response = await client.get(
        "/v1/companies/" + str(COMPANY) + "/accounts?limit=200", headers=ledger_headers()
    )
    cash = next(row for row in response.json()["items"] if row["kind"] == "CASH")
    policy = command.policy.model_copy(update={"sales_credit_allowed": False})
    base = command.model_copy(update={"policy": policy})
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(base)
    assert error.value.response.status_code == 422
    tender = {
        "account_id": cash["id"],
        "account_version": cash["row_version"],
        "tender": {
            "tender_key": uuid7(),
            "line_key": uuid7(),
            "mode": "CASH",
            "amount": "500",
            "currency": "INR",
        },
    }
    payload = base.model_dump(mode="json")
    payload["invoice"]["tenders"] = [tender]
    partial = InvoicePreviewCommand.model_validate(payload)
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(partial)
    assert error.value.response.status_code == 422
    tender["tender"]["amount"] = "900"
    payload["invoice"]["tenders"] = [tender]
    full = InvoicePreviewCommand.model_validate(payload)
    assert (await transport.preview(full)).payable == 900


async def test_sales_account_and_tax_restrictions_hold_at_owner(client, app):
    command, transport, _ = await setup(client, app)
    for restriction in (
        {"sales_party_account_ids": frozenset({uuid7()})},
        {"sales_supply_account_ids": frozenset({uuid7()})},
        {"sales_tax_profiles": frozenset({"INDIA_DOMESTIC_SERVICE"})},
    ):
        changed = command.model_copy(
            update={"policy": command.policy.model_copy(update=restriction)}
        )
        with pytest.raises(httpx.HTTPStatusError) as error:
            await transport.preview(changed)
        assert error.value.response.status_code == 422


async def test_independent_tax_allocation_requires_owner_policy(client, app):
    command, transport, _ = await setup(client, app)
    component = command.invoice.components[0].model_copy(
        update={
            "tax_targets": (command.invoice.supplies[0].line_key,),
            "tax_allocation_basis": "VALUE",
        }
    )
    changed = command.model_copy(
        update={
            "invoice": command.invoice.model_copy(update={"components": (component,)}),
        }
    )
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(changed)
    assert error.value.response.status_code == 422
    enabled = changed.model_copy(
        update={
            "policy": changed.policy.model_copy(
                update={
                    "independent_tax_allocation_allowed": True,
                }
            )
        }
    )
    result = await transport.preview(enabled)
    assert result.payable == 900
    assert [row.amount for row in result.allocations if row.purpose == "TAX_BASE"] == [-100]


@pytest.mark.parametrize(
    "actual,billed,other_unit",
    [("11", "10", False), ("10", "10", True)],
)
async def test_signed_preview_rejects_conflicting_ordinary_quantity_evidence(
    client, app, actual, billed, other_unit
):
    command, transport, _ = await setup(client, app)
    unit = uuid7()
    line = command.invoice.supplies[0].model_copy(
        update={
            "quantities": (
                InvoiceQuantity(basis="ACTUAL", quantity=actual, unit_id=unit),
                InvoiceQuantity(
                    basis="BILLED",
                    quantity=billed,
                    unit_id=uuid7() if other_unit else unit,
                ),
            )
        }
    )
    changed = command.model_copy(
        update={"invoice": command.invoice.model_copy(update={"supplies": (line,)})}
    )
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(changed)
    assert error.value.response.status_code == 422


async def test_invoice_preview_native_policy_and_owner_field_denies(client, app):
    command, transport, _ = await setup(client, app)
    restricted = command.model_copy(
        update={"policy": command.policy.model_copy(update={"manual_discounts_allowed": False})}
    )
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(restricted)
    assert error.value.response.status_code == 422

    delegated, _ = authority(
        policies=[
            {
                "entity_type": "accounting.account",
                "field_key": "kind",
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ]
    )
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(command.model_copy(update={"authority": delegated}))
    assert error.value.response.status_code == 403
    expired = verify_company_context(
        command.authority.company_context, command.authority.company_signature, SECRET.encode()
    )
    encoded, signature = sign_company_context(
        expired.model_copy(update={"issued_at": expired.issued_at - 120}), SECRET.encode()
    )
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(
            command.model_copy(
                update={
                    "authority": command.authority.model_copy(
                        update={"company_context": encoded, "company_signature": signature}
                    )
                }
            )
        )
    assert error.value.response.status_code == 401


async def test_invoice_preview_enforces_allocated_discount_limits(client, app):
    command, transport, _ = await setup(client, app)
    accepted = await transport.preview(command)
    assert accepted.payable == 900
    for update in (
        {"max_discount_pct": Decimal(9)},
        {"max_discount_amount": Decimal(99)},
        {"max_discount_components": 0},
        {"discount_input_kinds": frozenset({"FIXED"})},
    ):
        restricted = command.model_copy(update={"policy": command.policy.model_copy(update=update)})
        with pytest.raises(httpx.HTTPStatusError) as error:
            await transport.preview(restricted)
        assert error.value.response.status_code == 422


async def test_invoice_account_groups_are_protected_and_bound_to_acceptance(client, app):
    from accounting.models.masters import AccountGroup

    command, transport, _ = await setup(client, app)
    result = await transport.preview(command)
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            account = await db.get(Account, command.invoice.supplies[0].account_id)
            group = await db.get(AccountGroup, account.group_id)
            group.row_version += 1
    refreshed = await transport.preview(command)
    assert refreshed.payable == result.payable
    assert refreshed.calculation_hash != result.calculation_hash
    for entity, field in (
        ("account", "group_id"),
        ("account_group", "head_id"),
        ("account_head", "nature"),
    ):
        delegated, _ = authority(
            policies=[
                {
                    "entity_type": "accounting." + entity,
                    "field_key": field,
                    "access": "read",
                    "effect": "deny",
                    "scope_type": "company",
                    "scope_id": str(COMPANY),
                }
            ]
        )
        with pytest.raises(httpx.HTTPStatusError) as error:
            await transport.preview(command.model_copy(update={"authority": delegated}))
        assert error.value.response.status_code == 403
    forbidden = command.model_copy(
        update={
            "policy": command.policy.model_copy(
                update={"sales_supply_natures": frozenset({"ASSET"})}
            )
        }
    )
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(forbidden)
    assert error.value.response.status_code == 422

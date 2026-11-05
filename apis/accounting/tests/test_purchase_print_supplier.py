"""A Purchase print names the supplier party, never the payable account carrying its balance."""

import uuid

import httpx
import pytest
from billing_platform.company_context import sign_company_context, verify_company_context
from billing_platform.db import tenant_scope
from sqlalchemy import select
from voucher_execution.contracts import DelegatedAuthority
from voucher_execution.printing import PurchasePrintCommand

from accounting.models.masters import Account, Party
from accounting.tasks.invoice_execution import request_for
from tests.conftest import COMPANY, SECRET, TENANT
from tests.test_invoice_execution import invoice_command, run
from tests.test_invoice_preview import connection
from tests.test_ledger_api import LEDGER_PERMISSIONS, ledger_headers


def reader(*, without=(), policies=None):
    """A delegated actor holding vouchers.read and the ledger permissions except `without`."""
    permissions = (LEDGER_PERMISSIONS | {"vouchers.read"}) - set(without)
    values = ledger_headers(permissions=permissions, **({"policies": policies} if policies else {}))
    company = verify_company_context(
        values["X-Company-Context"], values["X-Company-Signature"], SECRET.encode()
    )
    context, signature = sign_company_context(
        company.model_copy(update={"policy_namespaces": frozenset({"accounting", "vouchers"})}),
        SECRET.encode(),
    )
    return DelegatedAuthority(
        actor_context=values["X-Actor-Context"],
        actor_signature=values["X-Actor-Signature"],
        company_context=context,
        company_signature=signature,
    )


def deny(entity, field):
    return {
        "entity_type": "accounting." + entity,
        "field_key": field,
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }


async def prepared(client, app):
    execution = await invoice_command(client, app, kind="PURCHASE")
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            account = await db.get(
                Account, uuid.UUID(execution.source_payload["invoice"]["party_account_id"])
            )
            party = await db.scalar(select(Party).where(Party.id == account.party_id))
    # The fixture's payable account and its party must be named differently for this to prove it.
    assert account.name != party.name
    transport = connection(client, app)

    def command(authority, *, posted=False):
        preview = request_for(execution).model_copy(update={"authority": authority})
        return PurchasePrintCommand(
            preview=preview, revision_id=execution.revision_id, require_posted=posted
        )

    return execution, account, party, transport, command


async def test_supplier_name_is_the_party_name_for_draft_and_posted_prints(client, app):
    execution, account, party, transport, command = await prepared(client, app)
    draft = await transport.purchase_print(command(reader()))
    assert draft.source == "PREVIEW"
    assert draft.supplier_name == party.name and draft.supplier_name != account.name
    assert (await run(app, execution)).outcome == "COMMITTED"
    posted = await transport.purchase_print(command(reader(), posted=True))
    assert posted.source == "POSTED"
    assert posted.supplier_name == party.name and posted.supplier_name != account.name


@pytest.mark.parametrize(
    "authority",
    [
        lambda: reader(without={"accounting.party.read"}),
        lambda: reader(policies=[deny("party", "name")]),
    ],
    ids=["no-party-read-permission", "party-name-read-denied"],
)
async def test_unreadable_party_name_is_withheld_not_replaced_by_the_account_name(
    client, app, authority
):
    execution, account, party, transport, command = await prepared(client, app)
    restricted = await transport.purchase_print(command(authority()))
    # None makes Vouchers print "Supplier details restricted"; amounts stay readable.
    assert restricted.supplier_name is None
    assert restricted.calculation.payable > 0


async def test_unreadable_account_name_still_refuses_the_print(client, app):
    execution, account, party, transport, command = await prepared(client, app)
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.purchase_print(command(reader(policies=[deny("account", "name")])))
    assert error.value.response.status_code == 403

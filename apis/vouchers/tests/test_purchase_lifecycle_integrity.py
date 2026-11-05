"""Purchase lifecycle integrity: a saved acceptance, supplier/ledger agreement, postable scope.

Each test pins one defect found by an independent review of the Purchase lifecycle. They use
the supported profile (the untaxed account/service bill) and the owner transport is faked
exactly where the real owner would be contacted.
"""

import copy
import datetime as dt
import secrets
import uuid
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.service_auth import CompanyServiceScope
from conftest import COMPANY, TENANT, headers
from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from test_foundation import create_type
from test_invoice_capture import invoice_body
from test_money_capture import money
from unit_source_factories import unit_masters
from voucher_execution.invoice import InvoiceCalculationDetail, InvoiceInput, InvoicePolicy
from voucher_execution.transport import ExecutionClient

from vouchers.domain.invoice import validate_invoice
from vouchers.models import core as m
from vouchers.schemas.documents import VoucherInput
from vouchers.schemas.owners import Owner
from vouchers.schemas.sources import SourceBundle
from vouchers.tasks.sources import apply_bundle

TODAY = dt.date.today().isoformat()
CALCULATION = "b" * 64
GOODS_REFUSAL = "Goods and mixed purchases cannot be accepted, submitted or posted yet"
# A ledger master replicated before Accounting published party links has no ``party_id`` key.
OLD = object()


async def project(app, masters, issuer="accounting"):
    await apply_bundle(
        app.state.session_factory,
        SourceBundle.model_validate(
            {
                "message_id": str(uuid7()),
                "tenant_id": str(TENANT),
                "company_id": str(COMPANY),
                "masters": masters,
            }
        ),
        issuer,
    )


def master(entity, source, **facts):
    return {
        "entity_type": entity,
        "source_id": str(source),
        "source_version": 1,
        "status": "ACTIVE",
        "facts": facts,
    }


async def seed(app, body, *, supplier, ledger_party):
    """Project one bill's accounts.

    ``ledger_party`` is the party the ledger belongs to, ``None`` for a ledger with no party
    (``party_id: null``, as Accounting publishes it), or ``OLD`` for evidence with no key at all.
    """
    ledger = body["party_account_id"]
    others = {row["account_id"] for row in body["supplies"]} - {ledger}
    link = (
        {}
        if ledger_party is OLD
        else {"party_id": None if ledger_party is None else str(ledger_party)}
    )
    await project(
        app,
        [
            master("party", supplier),
            master("account", ledger, kind="GENERAL", **link),
            *(master("account", account, kind="GENERAL") for account in others),
        ],
    )


def owner(app, monkeypatch, calculation=CALCULATION):
    """Configure the Accounting owner and fake only its signed preview call."""
    app.state.settings.execution_owner = Owner(
        owner="accounting",
        origin="http://127.0.0.1",
        key_id="purchase-integrity-test",
        secret=SecretStr(secrets.token_hex(32)),
        scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),),
    )
    calls = []

    async def preview(self, command):
        calls.append(command)
        payable = sum((Decimal(row.amount) for row in command.invoice.supplies), Decimal(0))
        return InvoiceCalculationDetail.model_validate(
            {
                "calculation_hash": calculation,
                "currency": command.currency,
                "commercial_total": str(payable),
                "tax_total": "0",
                "charged_tax_total": "0",
                "rounding": "0",
                "payable": str(payable),
                "lines": [],
                "components": [],
                "allocations": [],
                "tax_evidence": [],
            }
        )

    monkeypatch.setattr(ExecutionClient, "preview", preview)
    return calls


def request_for(kind, body, supplier, **changes):
    return {
        "type_revision_id": kind["revision_id"],
        "document_date": TODAY,
        "posting_date": TODAY,
        "currency": "INR",
        "narration": "Supplier bill",
        "invoice": body,
        "parties": [{"role": "SUPPLIER", "party_id": str(supplier), "source_version": 1}],
    } | changes


async def purchase(client, prefix, app, **changes):
    """A saved untaxed account/service Purchase draft whose ledger belongs to the supplier."""
    kind = await create_type(client, prefix, kind="PURCHASE", policy={"invoice": {}})
    body = invoice_body()
    body["components"] = []
    supplier = uuid7()
    await seed(app, body, supplier=supplier, ledger_party=supplier)
    request = request_for(kind, body, supplier, **changes)
    created = await client.post(prefix + "/vouchers", json=request, headers=headers())
    assert created.status_code == 201, created.text
    return created.json(), request


def path(prefix, document, tail=""):
    return prefix + "/vouchers/" + document["id"] + tail


async def accept(client, prefix, document, *, calculation=CALCULATION, version=None, key=None):
    return await client.post(
        path(prefix, document, "/invoice-acceptance"),
        json={
            "expected_version": version or document["row_version"],
            "calculation_hash": calculation,
        },
        headers=headers(key=key),
    )


async def submit(client, prefix, document, version=None):
    return await client.post(
        path(prefix, document, "/submit"),
        json={"expected_version": version or document["row_version"]},
        headers=headers(),
    )


# 1. A saved acceptance never survives an edit ---------------------------------------------


async def test_editing_an_accepted_invoice_clears_the_acceptance(client, prefix, app, monkeypatch):
    document, request = await purchase(client, prefix, app)
    owner(app, monkeypatch)
    accepted = await accept(client, prefix, document)
    assert accepted.status_code == 200, accepted.text
    detail = accepted.json()
    assert detail["invoice"]["accepted_calculation_hash"] == CALCULATION
    # A stale client round-trips the accepted invoice but changes what is owed.
    changed = copy.deepcopy(detail["invoice"])
    changed["supplies"][0]["amount"] = "9999"
    assert changed["accepted_calculation_hash"] == CALCULATION
    edited = await client.put(
        path(prefix, document),
        json={
            "expected_version": detail["row_version"],
            "content": request | {"invoice": changed},
        },
        headers=headers(),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["invoice"]["supplies"][0]["amount"] == "9999.0000"
    assert edited.json()["invoice"]["accepted_calculation_hash"] is None
    refused = await submit(client, prefix, edited.json())
    assert refused.status_code == 422, refused.text
    assert "accepted" in refused.json()["error"]["message"]


@pytest.mark.parametrize("change", ["narration", "posting_date", "document_date"])
async def test_any_edit_requires_a_fresh_acceptance(client, prefix, app, monkeypatch, change):
    document, request = await purchase(client, prefix, app)
    owner(app, monkeypatch)
    accepted = (await accept(client, prefix, document)).json()
    other = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    edit = {"narration": "Reworded"} if change == "narration" else {change: other}
    edited = await client.put(
        path(prefix, document),
        json={
            "expected_version": accepted["row_version"],
            "content": request | {"invoice": accepted["invoice"]} | edit,
        },
        headers=headers(),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["invoice"]["accepted_calculation_hash"] is None
    assert (await submit(client, prefix, edited.json())).status_code == 422


async def test_a_new_draft_cannot_carry_a_client_supplied_acceptance(
    client, prefix, app, monkeypatch
):
    kind = await create_type(client, prefix, kind="PURCHASE", policy={"invoice": {}})
    body = invoice_body()
    body["components"] = []
    supplier = uuid7()
    await seed(app, body, supplier=supplier, ledger_party=supplier)
    created = await client.post(
        prefix + "/vouchers",
        json=request_for(kind, body | {"accepted_calculation_hash": "a" * 64}, supplier),
        headers=headers(),
    )
    assert created.status_code == 201, created.text
    assert created.json()["invoice"]["accepted_calculation_hash"] is None
    assert (await submit(client, prefix, created.json())).status_code == 422


async def test_acceptance_is_verified_against_the_owner_preview_of_that_revision(
    client, prefix, app, monkeypatch
):
    document, _ = await purchase(client, prefix, app)
    calls = owner(app, monkeypatch)
    wrong = await accept(client, prefix, document, calculation="c" * 64)
    assert wrong.status_code == 409, wrong.text
    assert "calculation" in wrong.json()["error"]["message"]
    unchanged = await client.get(path(prefix, document), headers=headers())
    assert unchanged.json()["revision_number"] == document["revision_number"]
    assert unchanged.json()["invoice"]["accepted_calculation_hash"] is None
    key = secrets.token_hex(16)
    right = await accept(client, prefix, document, key=key)
    assert right.status_code == 200, right.text
    assert right.json()["invoice"]["accepted_calculation_hash"] == CALCULATION
    seen = len(calls)
    replay = await accept(client, prefix, document, key=key)
    assert replay.status_code == 200
    assert replay.json()["revision_id"] == right.json()["revision_id"]
    assert len(calls) == seen, "a replay must not contact the owner again"


async def test_acceptance_without_a_reachable_owner_is_refused_not_trusted(
    client, prefix, app, monkeypatch
):
    document, _ = await purchase(client, prefix, app)
    app.state.settings.execution_owner = None
    refused = await accept(client, prefix, document)
    assert refused.status_code in {409, 503}, refused.text
    unchanged = await client.get(path(prefix, document), headers=headers())
    assert unchanged.json()["invoice"]["accepted_calculation_hash"] is None


# 2. The header supplier must own the payable ledger ---------------------------------------


async def test_header_supplier_must_own_the_payable_ledger(client, prefix, app):
    kind = await create_type(client, prefix, kind="PURCHASE", policy={"invoice": {}})
    body = invoice_body()
    body["components"] = []
    header_supplier, other_supplier = uuid7(), uuid7()
    await seed(app, body, supplier=header_supplier, ledger_party=other_supplier)
    refused = await client.post(
        prefix + "/vouchers", json=request_for(kind, body, header_supplier), headers=headers()
    )
    assert refused.status_code == 422, refused.text
    message = refused.json()["error"]["message"]
    assert "party_account_id" in message and "SUPPLIER" in message


async def test_a_ledger_linked_to_no_party_does_not_stand_in_for_the_supplier(client, prefix, app):
    kind = await create_type(client, prefix, kind="PURCHASE", policy={"invoice": {}})
    body = invoice_body()
    body["components"] = []
    supplier = uuid7()
    await seed(app, body, supplier=supplier, ledger_party=None)
    refused = await client.post(
        prefix + "/vouchers", json=request_for(kind, body, supplier), headers=headers()
    )
    assert refused.status_code == 422, refused.text
    assert "party_account_id" in refused.json()["error"]["message"]


async def test_a_ledger_master_replicated_before_party_links_asks_for_resynchronisation(
    client, prefix, app
):
    """No ``party_id`` key at all is stale evidence, not a ledger that belongs to another party."""
    kind = await create_type(client, prefix, kind="PURCHASE", policy={"invoice": {}})
    body = invoice_body()
    body["components"] = []
    supplier = uuid7()
    await seed(app, body, supplier=supplier, ledger_party=OLD)
    refused = await client.post(
        prefix + "/vouchers", json=request_for(kind, body, supplier), headers=headers()
    )
    assert refused.status_code == 422, refused.text
    message = refused.json()["error"]["message"]
    assert "party_account_id" in message and "re-synchronise" in message
    assert "belongs to another party" not in message


async def test_the_matching_supplier_ledger_is_accepted(client, prefix, app):
    document, _ = await purchase(client, prefix, app)
    assert document["parties"][0]["role"] == "SUPPLIER"


async def test_a_purchase_cannot_carry_both_an_invoice_and_standalone_financial_entry(
    client, prefix, app
):
    """The post-time ``financial`` refusal is unreachable: the content contract excludes it."""
    kind = await create_type(client, prefix, kind="PURCHASE", policy={"invoice": {}})
    body = invoice_body()
    body["components"] = []
    supplier = uuid7()
    await seed(app, body, supplier=supplier, ledger_party=supplier)
    refused = await client.post(
        prefix + "/vouchers",
        json=request_for(kind, body, supplier, financial=money()),
        headers=headers(),
    )
    assert refused.status_code == 422, refused.text
    with pytest.raises(ValidationError, match="exclusive"):
        VoucherInput.model_validate(request_for(kind, body, supplier, financial=money()))


async def test_a_saved_mismatch_is_caught_again_at_submit(client, prefix, app, monkeypatch):
    """A draft whose ledger owner differs (saved before this check) cannot be submitted."""
    document, _ = await purchase(client, prefix, app)
    owner(app, monkeypatch)
    accepted = (await accept(client, prefix, document)).json()
    ledger = uuid.UUID(document["invoice"]["party_account_id"])
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            evidence = await db.scalar(
                select(m.VoucherMasterEvidence).where(
                    m.VoucherMasterEvidence.entity_type == "account",
                    m.VoucherMasterEvidence.source_id == ledger,
                )
            )
            evidence.facts = {**evidence.facts, "party_id": str(uuid7())}
    refused = await submit(client, prefix, accepted)
    assert refused.status_code == 422, refused.text
    assert "party_account_id" in refused.json()["error"]["message"]


# 3. Goods and mixed purchases are refused where acceptance is offered ----------------------


async def goods_purchase(client, prefix, app, *, mixed):
    item, unit, line = uuid7(), uuid7(), uuid7()
    supplier = uuid7()
    kind = await create_type(
        client,
        prefix,
        kind="PURCHASE",
        policy={
            "schema_version": 2,
            "invoice": {},
            "default_mode": "MIXED" if mixed else "ITEMS",
            "allowed_modes": ["ITEMS", "MIXED", "ACCOUNTS"],
        },
    )
    body = invoice_body()
    body["components"] = []
    quantity = [
        {"basis": "ACTUAL", "quantity": "1", "unit_id": str(unit)},
        {"basis": "BILLED", "quantity": "1", "unit_id": str(unit)},
    ]
    body["supplies"][0].update(
        line_key=str(line), supply_kind="GOODS", item_line_key=str(line), quantities=quantity
    )
    if mixed:
        body["supplies"].append(
            body["supplies"][0]
            | {
                "line_key": str(uuid7()),
                "supply_kind": "SERVICE",
                "item_line_key": None,
                "quantities": [],
            }
        )
    await seed(app, body, supplier=supplier, ledger_party=supplier)
    await project(
        app,
        [
            *unit_masters(item, unit),
            master(
                "item_transaction_policy",
                item,
                kind="GOODS",
                inventory_mode="STOCK",
                item_version=1,
                sellable=True,
                purchasable=True,
            ),
        ],
        "catalog",
    )
    request = request_for(
        kind,
        body,
        supplier,
        mode="MIXED" if mixed else "ITEMS",
        lines=[
            {
                "line_key": str(line),
                "item": {
                    "item_id": str(item),
                    "item_version": 1,
                    "unit_id": str(unit),
                    "actual_quantity": "1",
                    "billed_quantity": "1",
                },
            }
        ],
    )
    created = await client.post(prefix + "/vouchers", json=request, headers=headers())
    assert created.status_code == 201, created.text
    return created.json()


@pytest.mark.parametrize("mixed", [False, True], ids=["goods", "mixed"])
async def test_goods_and_mixed_purchases_are_refused_at_acceptance(
    client, prefix, app, monkeypatch, mixed
):
    document = await goods_purchase(client, prefix, app, mixed=mixed)
    owner(app, monkeypatch)
    refused = await accept(client, prefix, document)
    assert refused.status_code in {409, 422}, refused.text
    assert GOODS_REFUSAL in refused.json()["error"]["message"]
    unchanged = await client.get(path(prefix, document), headers=headers())
    assert unchanged.json()["revision_number"] == document["revision_number"]
    assert unchanged.json()["invoice"]["accepted_calculation_hash"] is None


def purchase_content(*, mode="ACCOUNTS", goods=False, hash_="a" * 64):
    body = invoice_body()
    body["components"] = []
    body["accepted_calculation_hash"] = hash_
    lines = []
    if goods:
        line, unit = uuid7(), uuid7()
        body["supplies"][0].update(
            line_key=str(line),
            supply_kind="GOODS",
            item_line_key=str(line),
            quantities=[
                {"basis": "ACTUAL", "quantity": "1", "unit_id": str(unit)},
                {"basis": "BILLED", "quantity": "1", "unit_id": str(unit)},
            ],
        )
        lines = [
            {
                "line_key": str(line),
                "item": {
                    "item_id": str(uuid7()),
                    "item_version": 1,
                    "unit_id": str(unit),
                    "actual_quantity": "1",
                    "billed_quantity": "1",
                },
            }
        ]
    return VoucherInput.model_validate(
        {
            "type_revision_id": str(uuid7()),
            "document_date": TODAY,
            "posting_date": TODAY,
            "currency": "INR",
            "mode": mode,
            "invoice": body,
            "lines": lines,
        }
    )


@pytest.mark.parametrize(
    "content",
    [
        purchase_content(mode="ITEMS", goods=True),
        purchase_content(mode="MIXED", goods=True),
        purchase_content(mode="ITEMS"),
        purchase_content(mode="MIXED"),
    ],
    ids=["goods", "mixed", "items-mode", "mixed-mode"],
)
def test_goods_and_mixed_purchases_cannot_be_submitted_even_with_a_hash(content):
    validate_invoice(content, InvoicePolicy(), kind="PURCHASE", profile="STANDARD", stage="DRAFT")
    with pytest.raises(ValidationFailedError, match=GOODS_REFUSAL):
        validate_invoice(
            content, InvoicePolicy(), kind="PURCHASE", profile="STANDARD", stage="SUBMITTED"
        )


def test_account_and_service_purchases_and_every_other_kind_are_unchanged():
    validate_invoice(
        purchase_content(), InvoicePolicy(), kind="PURCHASE", profile="STANDARD", stage="SUBMITTED"
    )
    goods = purchase_content(mode="ITEMS", goods=True)
    for kind in ("SALES", "CREDIT_NOTE", "DEBIT_NOTE"):
        note = {"source_invoice_id": str(uuid7())} if kind != "SALES" else {}
        invoice = InvoiceInput.model_validate(goods.invoice.model_dump(mode="json") | note)
        validate_invoice(
            goods.model_copy(update={"invoice": invoice}),
            InvoicePolicy(),
            kind=kind,
            profile="STANDARD",
            stage="SUBMITTED",
        )

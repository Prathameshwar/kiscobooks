"""Purchase bill review 2026-11-02: history of a withdrawn approval, one bill number per bill."""

import copy

import pytest
from billing_platform.ids import uuid7
from conftest import headers
from test_purchase_approval_flow import NO_APPROVAL, accept_as, act, bill
from test_purchase_lifecycle_integrity import accept, owner, path, purchase, submit


async def test_editing_an_approved_bill_records_that_its_approval_was_withdrawn(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    user = uuid7()
    document, request = await bill(client, prefix, app, NO_APPROVAL, user=user)
    accepted = await accept_as(client, prefix, document, user)
    approved = (await act(client, prefix, accepted, "submit", user)).json()
    assert approved["status"] == "APPROVED"
    edited = await client.put(
        path(prefix, approved),
        json={
            "expected_version": approved["row_version"],
            "content": request | {"narration": "Reworded"},
        },
        headers=headers(user=user),
    )
    assert edited.status_code == 200, edited.text
    history = await client.get(path(prefix, approved, "/history"), headers=headers())
    assert history.status_code == 200, history.text
    last = history.json()["items"][-1]
    assert (last["action"], last["from_status"], last["to_status"]) == (
        "reopen",
        "APPROVED",
        "DRAFT",
    )
    assert last["revision_id"] == edited.json()["revision_id"]


async def test_a_draft_edit_adds_no_history_step(client, prefix, app):
    document, request = await purchase(client, prefix, app)
    edited = await client.put(
        path(prefix, document),
        json={
            "expected_version": document["row_version"],
            "content": request | {"narration": "Reworded"},
        },
        headers=headers(),
    )
    assert edited.status_code == 200, edited.text
    history = await client.get(path(prefix, document, "/history"), headers=headers())
    assert history.json()["items"] == []


async def submitted_with(client, prefix, app, monkeypatch, change):
    owner(app, monkeypatch)
    document, request = await purchase(client, prefix, app)
    invoice = copy.deepcopy(request["invoice"])
    change(invoice)
    edited = await client.put(
        path(prefix, document),
        json={
            "expected_version": document["row_version"],
            "content": request | {"invoice": invoice},
        },
        headers=headers(),
    )
    assert edited.status_code == 200, edited.text
    accepted = await accept(client, prefix, edited.json())
    if accepted.status_code != 200:
        return accepted
    return await submit(client, prefix, accepted.json())


async def test_a_bill_number_that_is_only_punctuation_cannot_be_submitted(
    client, prefix, app, monkeypatch
):
    def blank(invoice):
        invoice["bill_reference"] = " . "

    refused = await submitted_with(client, prefix, app, monkeypatch, blank)
    assert refused.status_code == 422, refused.text
    assert "bill number" in refused.json()["error"]["message"]


async def test_the_gst_supplier_invoice_number_must_be_the_bill_number(
    client, prefix, app, monkeypatch
):
    def differ(invoice):
        invoice["bill_reference"] = "INV-1001/B"
        invoice["tax"] = (invoice.get("tax") or {"profile": "UNTAXED_ACCOUNT"}) | {
            "supplier_invoice_number": "INV-1001"
        }

    refused = await submitted_with(client, prefix, app, monkeypatch, differ)
    assert refused.status_code == 422, refused.text
    assert "must match" in refused.json()["error"]["message"]


async def test_a_bill_number_differing_only_in_case_and_spacing_matches(
    client, prefix, app, monkeypatch
):
    def same(invoice):
        invoice["bill_reference"] = "inv-1001 "
        invoice["tax"] = (invoice.get("tax") or {"profile": "UNTAXED_ACCOUNT"}) | {
            "supplier_invoice_number": "INV-1001"
        }

    submitted = await submitted_with(client, prefix, app, monkeypatch, same)
    assert submitted.status_code == 200, submitted.text


def test_an_owner_refusal_names_its_reason_and_falls_back_safely():
    import httpx

    from vouchers.api.invoices import refusal

    reason = {
        "error": {
            "code": "validation_failed",
            "message": "invoice must have positive consideration",
        }
    }
    assert refusal(httpx.Response(422, json=reason)) == (
        "invoice calculation was refused: invoice must have positive consideration"
    )
    for body in ({"detail": "x"}, {"error": {"message": ""}}, {"error": {"message": "x" * 301}}):
        assert "verify accounts" in refusal(httpx.Response(409, json=body))
    assert "verify accounts" in refusal(httpx.Response(409, text="<html>"))


# Purchase with Product review --------------------------------------------------------------


async def itemised_purchase_without_invoice(client, prefix, app):
    from test_foundation import create_type
    from test_purchase_lifecycle_integrity import master, project
    from unit_source_factories import unit_masters

    item, unit, line = uuid7(), uuid7(), uuid7()
    kind = await create_type(
        client,
        prefix,
        code="GOODS_NO_INVOICE",
        kind="PURCHASE",
        policy={
            "schema_version": 2,
            "default_mode": "ITEMS",
            "allowed_modes": ["ITEMS"],
            "approval_required": False,
        },
    )
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
    import datetime as dt

    created = await client.post(
        prefix + "/vouchers",
        json={
            "type_revision_id": kind["revision_id"],
            "document_date": dt.date.today().isoformat(),
            "currency": "INR",
            "narration": "Goods without a bill section",
            "mode": "ITEMS",
            "lines": [
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
        },
        headers=headers(),
    )
    assert created.status_code == 201, created.text
    return created.json()


async def test_a_goods_purchase_without_an_invoice_section_cannot_be_submitted(client, prefix, app):
    from test_purchase_lifecycle_integrity import GOODS_REFUSAL

    document = await itemised_purchase_without_invoice(client, prefix, app)
    refused = await submit(client, prefix, document)
    assert refused.status_code == 422, refused.text
    assert GOODS_REFUSAL in refused.json()["error"]["message"]
    current = await client.get(path(prefix, document), headers=headers())
    assert current.json()["status"] == "DRAFT"


def test_the_goods_boundary_holds_at_every_stage_with_or_without_an_invoice():
    import datetime as dt

    import pytest
    from billing_platform.errors import ValidationFailedError
    from voucher_execution.invoice import InvoicePolicy

    from vouchers.domain.invoice import UNPOSTABLE_PURCHASE, validate_invoice
    from vouchers.schemas.documents import VoucherInput

    body = VoucherInput.model_validate(
        {
            "type_revision_id": str(uuid7()),
            "document_date": dt.date.today().isoformat(),
            "currency": "INR",
            "mode": "ITEMS",
        }
    )
    for stage in ("SUBMITTED", "APPROVED", "ISSUED", "POST"):
        with pytest.raises(ValidationFailedError, match="Goods and mixed"):
            validate_invoice(
                body, InvoicePolicy(), kind="PURCHASE", profile="STANDARD", stage=stage
            )
    validate_invoice(body, InvoicePolicy(), kind="PURCHASE", profile="STANDARD", stage="DRAFT")
    accounts = body.model_copy(update={"mode": "ACCOUNTS"})
    validate_invoice(accounts, InvoicePolicy(), kind="PURCHASE", profile="STANDARD", stage="POST")
    assert UNPOSTABLE_PURCHASE.startswith("Goods and mixed")


@pytest.mark.parametrize(
    "policy",
    [
        {"invoice": {}, "default_mode": "ITEMS", "allowed_modes": ["ITEMS"]},
        {"invoice": {}, "default_mode": "MIXED", "allowed_modes": ["ITEMS", "MIXED"]},
        {"invoice": {}, "required_sections": ["ITEMS"], "allowed_modes": ["ACCOUNTS", "ITEMS"]},
    ],
)
async def test_a_product_or_mixed_purchase_type_is_refused_for_import(client, prefix, policy):
    from test_foundation import create_type
    from test_imports_api import auth

    kind = await create_type(client, prefix, code="PRODUCT_BILL", kind="PURCHASE", policy=policy)
    template = await client.get(
        prefix + "/voucher-import-templates",
        params={"voucher_type_id": kind["id"], "format": "CSV"},
        headers=auth(),
    )
    assert template.status_code == 409, template.text
    assert "product and mixed bills cannot be imported" in template.text


async def test_an_account_purchase_type_still_offers_its_import_template(client, prefix):
    from test_imports_api import auth, purchase_type

    kind = await purchase_type(client, prefix)
    template = await client.get(
        prefix + "/voucher-import-templates",
        params={"voucher_type_id": kind["id"], "format": "CSV"},
        headers=auth(),
    )
    assert template.status_code == 200, template.text


@pytest.mark.parametrize("mixed", [False, True])
async def test_a_product_bill_is_not_printed_without_its_goods(
    client, prefix, app, tmp_path, monkeypatch, mixed
):
    import secrets

    from billing_platform.service_auth import CompanyServiceScope
    from conftest import COMPANY, TENANT
    from pydantic import SecretStr
    from test_purchase_lifecycle_integrity import goods_purchase
    from voucher_execution.transport import ExecutionClient

    from vouchers.schemas.owners import Owner

    saved = await goods_purchase(client, prefix, app, mixed=mixed)
    scope = CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY)
    app.state.settings.print_file_root = tmp_path
    app.state.settings.print_broker_url = SecretStr("amqp://127.0.0.1")
    app.state.settings.print_scopes = [scope]
    app.state.settings.execution_owner = Owner(
        owner="accounting",
        origin="http://127.0.0.1",
        key_id="print-test",
        secret=SecretStr(secrets.token_hex(32)),
        scopes=(scope,),
    )
    calls = []

    async def owner(self, command):
        calls.append(command)
        raise AssertionError("the owner is not asked for a bill that cannot print")

    monkeypatch.setattr(ExecutionClient, "purchase_print", owner)
    from billing_platform.company_context import sign_company_context, verify_company_context
    from billing_platform.display import DisplayConfiguration
    from conftest import SECRET
    from test_purchase_print import snapshot

    signed = headers()
    company = verify_company_context(
        signed["X-Company-Context"], signed["X-Company-Signature"], SECRET.encode()
    )
    signed["X-Company-Context"], signed["X-Company-Signature"] = sign_company_context(
        company.model_copy(
            update={"report_display": DisplayConfiguration.model_validate(snapshot()["display"])}
        ),
        SECRET.encode(),
    )
    result = await client.post(
        path(prefix, saved, "/print-jobs"),
        headers=signed,
        json={"expected_version": saved["row_version"], "revision_id": saved["revision_id"]},
    )
    assert result.status_code == 409, result.text
    # Goods bills print since 2026-11-04 (designer plan R1), but only with their stock lines.
    assert "do not match its stock lines" in result.json()["error"]["message"]
    assert calls == []

import datetime as dt
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT, headers
from pydantic import ValidationError
from sqlalchemy import select
from test_foundation import create_type, draft
from voucher_execution.money import MoneyInput, MoneyPolicy

from vouchers.domain.configuration import intersect
from vouchers.domain.documents import validate_content
from vouchers.domain.financial import validate_money
from vouchers.models import core as m
from vouchers.schemas.configuration import MoneyConfiguration, Policy
from vouchers.schemas.documents import VoucherInput
from vouchers.schemas.sources import SourceBundle
from vouchers.tasks.sources import apply_bundle


def money():
    keys = [str(uuid7()), str(uuid7())]
    return {
        "purpose": "GENERAL",
        "accounts": [
            {
                "line_key": key,
                "account_id": str(uuid7()),
                "source_version": 1,
                "side": side,
                "amount": "123.4500",
                "currency": "INR",
            }
            for key, side in zip(keys, ("DEBIT", "CREDIT"), strict=True)
        ],
    }


async def project(app, entries):
    bundle = SourceBundle.model_validate(
        {
            "message_id": str(uuid7()),
            "tenant_id": str(TENANT),
            "company_id": str(COMPANY),
            "masters": [
                {
                    "entity_type": "account",
                    "source_id": row["account_id"],
                    "source_version": 1,
                    "status": "ACTIVE",
                    "facts": {"kind": "GENERAL"},
                }
                for row in entries
            ],
        }
    )
    await apply_bundle(app.state.session_factory, bundle, "accounting")


async def test_native_financial_capture_revision_idempotency_and_masking(client, prefix, app):
    kind = await create_type(client, prefix, kind="JOURNAL")
    body = money()
    await project(app, body["accounts"])
    item, request = await draft(client, prefix, kind["revision_id"], financial=body)
    assert item["financial"]["accounts"][0]["amount"] == "123.4500"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = list(
                await db.scalars(
                    select(m.VoucherAccountDetail).order_by(m.VoucherAccountDetail.sequence)
                )
            )
            assert len(rows) == 2 and isinstance(rows[0].amount, Decimal)
            assert rows[0].amount == Decimal("123.45")
            rows[0].amount = Decimal("10")
            with pytest.raises(ConflictError):
                await db.flush()
    denied = [
        {
            "entity_type": "vouchers.voucher",
            "field_key": "financial",
            "access": "read",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        }
    ]
    masked = await client.get(prefix + "/vouchers/" + item["id"], headers=headers(policies=denied))
    assert masked.status_code == 200 and masked.json().get("financial") is None
    blocked = await client.post(
        prefix + "/vouchers",
        json=request,
        headers=headers(policies=[denied[0] | {"access": "write"}]),
    )
    assert blocked.status_code == 403
    again = headers()
    created = await client.post(prefix + "/vouchers", json=request, headers=again)
    replay = await client.post(prefix + "/vouchers", json=request, headers=again)
    assert created.json()["id"] == replay.json()["id"]
    assert replay.headers["Idempotency-Replayed"] == "true"


async def test_tenders_and_existing_bill_targets_round_trip(client, prefix, app):
    kind = await create_type(client, prefix, kind="PAYMENT")
    body = money() | {"purpose": "SETTLEMENT"}
    body["tenders"] = [
        {
            "tender_key": str(uuid7()),
            "line_key": body["accounts"][1]["line_key"],
            "mode": "CHEQUE",
            "amount": "123.4500",
            "currency": "INR",
            "reference": "CHQ-123",
            "instrument_date": dt.date.today().isoformat(),
        }
    ]
    body["allocations"] = [
        {
            "allocation_key": str(uuid7()),
            "debt": {"item_id": str(uuid7())},
            "credit": {"item_id": str(uuid7())},
            "amount": "100.0000",
            "currency": "INR",
        }
    ]
    await project(app, body["accounts"])
    item, _ = await draft(client, prefix, kind["revision_id"], financial=body)
    stored = item["financial"]
    assert stored["tenders"][0]["reference"] == "CHQ-123"
    assert stored["allocations"][0]["amount"] == "100.0000"


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", 1.1),
        ("amount", "0"),
        ("amount", "0.00001"),
        ("exchange_rate", "0"),
        ("exchange_rate", "NaN"),
    ],
)
def test_native_money_rejects_lossy_values(field, value):
    body = money()
    body["accounts"][0][field] = value
    with pytest.raises(ValidationError):
        MoneyInput.model_validate(body)


def test_tracking_tenders_and_policy_cannot_be_widened():
    body = money()
    body["tenders"] = [
        {
            "tender_key": str(uuid7()),
            "line_key": body["accounts"][0]["line_key"],
            "mode": "CASH",
            "amount": "1",
            "currency": "INR",
        }
    ]
    with pytest.raises(ValidationError, match="exactly cover"):
        MoneyInput.model_validate(body)
    body.pop("tenders")
    body["accounts"][0]["tracking"] = "NEW_REF"
    with pytest.raises(ValidationError, match="new reference requires a reference"):
        MoneyInput.model_validate(body)
    # A due date is optional: Accounting dates the bill on its document date without one.
    body["accounts"][0]["bill_reference"] = "BILL-1"
    assert MoneyInput.model_validate(body).accounts[0].due_date is None
    body["accounts"][0].pop("bill_reference")
    body["accounts"][0]["tracking"] = "NONE"
    parent = Policy(
        financial=MoneyPolicy(
            allowed_payment_modes=frozenset({"CASH"}), split_tenders_allowed=False
        )
    )
    child = Policy(financial=MoneyPolicy())
    result = intersect(parent, child).financial
    assert result and result.allowed_payment_modes == {"CASH"} and not result.split_tenders_allowed
    with pytest.raises(ValidationFailedError):
        validate_money(
            MoneyInput.model_validate(money()),
            result,
            kind="CONTRA",
            profile="STANDARD",
            posting_date=None,
        )


def test_a_bank_tender_reference_is_optional_but_cash_and_cheque_rules_hold():
    body = money()
    tender = {
        "tender_key": str(uuid7()),
        "line_key": body["accounts"][1]["line_key"],
        "amount": "123.4500",
        "currency": "INR",
    }
    for mode in ("NEFT", "UPI", "CARD", "BANK_TRANSFER"):
        accepted = MoneyInput.model_validate(body | {"tenders": [tender | {"mode": mode}]})
        assert accepted.tenders[0].reference is None
    with pytest.raises(ValidationError, match="cash has no banking instrument"):
        MoneyInput.model_validate(
            body | {"tenders": [tender | {"mode": "CASH", "reference": "X"}]}
        )
    with pytest.raises(ValidationError, match="cheque date is required"):
        MoneyInput.model_validate(body | {"tenders": [tender | {"mode": "CHEQUE"}]})


def test_v2_money_purpose_and_tender_restrictions_are_enforced():
    day = dt.date(2026, 4, 1)
    body = money()
    content = VoucherInput.model_validate(
        {
            "type_revision_id": str(uuid7()),
            "document_date": day,
            "posting_date": day,
            "currency": "INR",
            "financial": body,
        }
    )
    purpose_policy = Policy(
        schema_version=2,
        money=MoneyConfiguration(allowed_purposes=frozenset({"SETTLEMENT"})),
    )
    with pytest.raises(ValidationFailedError, match="contradictory inherited money"):
        intersect(
            purpose_policy,
            Policy(
                schema_version=2,
                money=MoneyConfiguration(allowed_purposes=frozenset({"REFUND"})),
            ),
        )
    with pytest.raises(ValidationFailedError, match="purpose or tender"):
        validate_content(
            content, purpose_policy, kind="JOURNAL", profile="STANDARD", stage="DRAFT", today=day
        )
    body["tenders"] = [
        {
            "tender_key": str(uuid7()),
            "line_key": body["accounts"][0]["line_key"],
            "mode": "CASH",
            "amount": "123.4500",
            "currency": "INR",
        }
    ]
    content = VoucherInput.model_validate(
        content.model_dump(exclude={"financial"}) | {"financial": body}
    )
    tender_policy = Policy(schema_version=2, money=MoneyConfiguration(max_tenders=0))
    with pytest.raises(ValidationFailedError, match="purpose or tender"):
        validate_content(
            content, tender_policy, kind="JOURNAL", profile="STANDARD", stage="DRAFT", today=day
        )

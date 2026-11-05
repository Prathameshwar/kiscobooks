"""Catalog evidence is authenticated, source-bound and balanced with charge posting."""

import secrets
import time
from decimal import Decimal
from typing import Any

import httpx
import pytest
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.service_auth import CompanyServiceScope, ServiceKey, sign_service_body
from fastapi import FastAPI
from pydantic import SecretStr

from accounting.config import CatalogTaxCredential
from accounting.tasks.charge_tax import OPERATION
from tests.conftest import COMPANY, TENANT, headers
from tests.test_charges_api import approve, assessment, setup_charge
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import ledger_headers
from tests.test_masters import activate, post
from tests.test_openings_sources import post_source

REGULAR = {
    "id": str(uuid7()),
    "tax_system": "gst_in",
    "regime": "regular",
    "jurisdiction_code": "IN-MH",
    "valid_from": "2026-04-01",
    "valid_to": None,
    "registration_class": "supplier",
}
#: A second regular registration, so an account bound to it is a wrong-registration account.
OTHER = REGULAR | {"id": str(uuid7()), "jurisdiction_code": "IN-KA"}
COMPOSITION = REGULAR | {"id": str(uuid7()), "regime": "composition", "jurisdiction_code": "IN-GA"}
#: Ended before the 2026-04-13 posting date: a registration gap.
ENDED = REGULAR | {
    "id": str(uuid7()),
    "jurisdiction_code": "IN-TN",
    "valid_from": "2026-01-01",
    "valid_to": "2026-04-10",
}
#: An Input Service Distributor GSTIN may coexist with the supplier one; it never charges.
ISD = REGULAR | {
    "id": str(uuid7()),
    "regime": "isd",
    "jurisdiction_code": "IN-DL",
    "registration_class": "isd",
}
#: A context whose class disagrees with the regime fails closed.
MISLABELED = REGULAR | {
    "id": str(uuid7()),
    "jurisdiction_code": "IN-RJ",
    "registration_class": "tds_deductor",
}
CONTEXT = [REGULAR, OTHER, COMPOSITION, ENDED, ISD, MISLABELED]
#: Request-model refusals (typed codes, allowed sets, a required registration) share one message.
SCHEMA = "request validation failed"
SUPPLIER = "not a supplier registration"
PROFILE = "output tax account of that component under the charging registration"


def evidence_headers(**kwargs: Any) -> dict[str, str]:
    return ledger_headers(registrations=CONTEXT, **kwargs)


async def gst_account(
    client: httpx.AsyncClient, group: str, component: str, registration: dict[str, Any]
) -> dict[str, Any]:
    h = headers(registrations=CONTEXT)
    account = await post(
        client,
        "/accounts",
        {
            "code": f"OUT_{component}_{registration['id'][-4:]}",
            "name": "GST",
            "group_id": group,
            "kind": "TAX",
        },
        h=h,
    )
    await post(
        client,
        "/account-tax-profiles",
        {
            "account_id": account["id"],
            "company_registration_id": registration["id"],
            "scheme": "GST_IN",
            "component": component,
            "duty_type": "GST",
            "purpose": "OUTPUT_PAYABLE",
        },
        h=h,
    )
    return await activate(client, "/accounts", account, h=h)


async def withholding_account(client: httpx.AsyncClient, group: str) -> dict[str, Any]:
    """A TAX account whose profile is a TDS liability, not a GST output component."""
    account = await post(
        client,
        "/accounts",
        {"code": "PROFILED_TAX", "name": "Tax payable", "group_id": group, "kind": "TAX"},
    )
    await post(
        client,
        "/account-tax-profiles",
        {
            "account_id": account["id"],
            "scheme": "OTHER",
            "component": "OTHER",
            "duty_type": "TDS",
            "purpose": "OUTPUT_PAYABLE",
        },
    )
    return await activate(client, "/accounts", account)


class Signer:
    def __init__(self, app: FastAPI) -> None:
        self.secret = secrets.token_hex(32)
        app.state.settings.catalog_tax_credentials = {
            "catalog.test": CatalogTaxCredential(
                secret=SecretStr(self.secret),
                scopes=[CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY)],
            )
        }

    def body(self, computation: dict[str, Any], accounts: dict[str, str]) -> dict[str, Any]:
        timestamp = int(time.time())
        return {
            "key_id": "catalog.test",
            "timestamp": timestamp,
            "computation": computation,
            "accounts": accounts,
            "signature": sign_service_body(
                ServiceKey("catalog", "accounting", frozenset({OPERATION}), self.secret.encode()),
                key_id="catalog.test",
                operation=OPERATION,
                timestamp=timestamp,
                body=canonical_json(computation),
            ),
        }


def computation(
    row: dict[str, Any],
    posting_date: str,
    components: list[tuple[str, str]],
    *,
    registration: dict[str, Any] | None = REGULAR,
    version: int = 2,
    currency: str = "INR",
) -> dict[str, Any]:
    tax = sum((Decimal(amount) for _, amount in components), Decimal(0))
    value: dict[str, Any] = {
        "version": version,
        "provider_id": str(uuid7()),
        "tenant_id": str(TENANT),
        "company_id": str(COMPANY),
        "assessment_id": row["id"],
        "input_hash": row["input_hash"],
        "posting_date": posting_date,
        "currency": currency,
        "net_amount": "1",
        "gross_amount": str(Decimal(1) + tax),
        "components": [{"code": code, "amount": amount} for code, amount in components],
    }
    if version == 2:
        value["company_registration_id"] = registration["id"] if registration else None
    return value


async def tax_group(client: httpx.AsyncClient) -> str:
    groups = (
        await client.get(BASE + "/account-groups?limit=200", headers=ledger_headers())
    ).json()["items"]
    return str(next(group for group in groups if group["code"] == "TAX_PAYABLE")["id"])


@pytest.mark.parametrize(
    "currency,rate,expected_balance", [("INR", "1", "101.18"), ("USD", "2.555", "258.51")]
)
async def test_taxable_charge_needs_verified_catalog_evidence(
    client: httpx.AsyncClient, app: FastAPI, currency: str, rate: str, expected_balance: str
) -> None:
    request, account, _, _ = await setup_charge(
        client, app, tax_treatment="EXTERNAL", currency=currency, exchange_rate=rate
    )
    row = await assessment(client, request)
    assert (await approve(client, row, features={"multi_currency"})).status_code == 409
    signer = Signer(app)
    secret = signer.secret
    group = await tax_group(client)
    cgst = await gst_account(client, group, "CGST", REGULAR)
    sgst = await gst_account(client, group, "SGST", REGULAR)
    body = signer.body(
        computation(
            row, request["posting_date"], [("CGST", "0.09"), ("SGST", "0.09")], currency=currency
        ),
        {"CGST": cgst["id"], "SGST": sgst["id"]},
    )
    tampered = body | {"computation": body["computation"] | {"gross_amount": "1.19"}}
    assert (
        await client.post(BASE + "/charge-tax-snapshots", json=tampered, headers=ledger_headers())
    ).status_code == 401

    def signed(changes: dict[str, Any]) -> dict[str, Any]:
        candidate = body | changes
        return candidate | {
            "signature": sign_service_body(
                ServiceKey("catalog", "accounting", frozenset({OPERATION}), secret.encode()),
                key_id="catalog.test",
                operation=OPERATION,
                timestamp=candidate["timestamp"],
                body=canonical_json(candidate["computation"]),
            )
        }

    candidates = [
        (body | {"key_id": "unknown"}, 403),
        (signed({"timestamp": body["timestamp"] - 600}), 401),
        (signed({"computation": body["computation"] | {"company_id": str(uuid7())}}), 403),
        (signed({"computation": body["computation"] | {"input_hash": "b" * 64}}), 409),
        (signed({"computation": body["computation"] | {"gross_amount": "1.19"}}), 422),
        (
            signed(
                {
                    "computation": body["computation"]
                    | {
                        "components": [
                            *body["computation"]["components"],
                            *body["computation"]["components"],
                        ]
                    }
                }
            ),
            422,
        ),
        (body | {"accounts": {"CGST": account["id"], "SGST": sgst["id"]}}, 422),
        (body | {"accounts": {}}, 422),
    ]
    for candidate, status in candidates:
        denied = await client.post(
            BASE + "/charge-tax-snapshots", json=candidate, headers=evidence_headers()
        )
        assert denied.status_code == status, denied.text
    from tests.test_finance_review2 import policy

    private_account = await client.post(
        BASE + "/charge-tax-snapshots",
        json=body,
        headers=evidence_headers(policies=[policy("account", "kind")]),
    )
    assert private_account.status_code == 403, private_account.text
    result = await client.post(
        BASE + "/charge-tax-snapshots", json=body, headers=evidence_headers(key="catalog-evidence")
    )
    assert result.status_code == 201, result.text
    replay = await client.post(
        BASE + "/charge-tax-snapshots", json=body, headers=evidence_headers(key="catalog-evidence")
    )
    assert replay.status_code == 201 and replay.json()["id"] == result.json()["id"]
    same_source = await client.post(
        BASE + "/charge-tax-snapshots", json=body, headers=evidence_headers()
    )
    assert same_source.status_code == 201 and same_source.json()["id"] == result.json()["id"]
    changed_source = await client.post(
        BASE + "/charge-tax-snapshots",
        json=signed({"computation": body["computation"] | {"provider_id": str(uuid7())}}),
        headers=evidence_headers(),
    )
    assert changed_source.status_code == 409
    if currency == "USD":
        missing_mapping = await approve(client, row, features={"multi_currency"})
        assert missing_mapping.status_code == 409, missing_mapping.text
        from tests.test_masters import post

        accounts = (
            await client.get(BASE + "/accounts?limit=200", headers=ledger_headers())
        ).json()["items"]
        expense = next(a for a in accounts if a["code"] == "ROUNDING_LOSS")
        mapping = await post(
            client,
            "/posting-mapping-drafts",
            {
                "values": {
                    "purpose": "ROUNDING_LOSS",
                    "account_id": expense["id"],
                    "currency": "INR",
                    "valid_from": "2026-04-01",
                }
            },
        )
        published = await client.post(
            BASE + f"/posting-mapping-drafts/{mapping['id']}/publish",
            json={"expected_version": mapping["row_version"]},
            headers=ledger_headers(),
        )
        assert published.status_code == 200, published.text
    approved = await approve(client, row, features={"multi_currency"})
    assert approved.status_code == 200, approved.text
    posted = await post_source(client, approved.json())
    assert posted.status_code == 200, posted.text
    balance = await client.get(
        BASE + "/ledger/balance",
        params={"as_of": "2026-04-13", "currency": "INR", "account_id": account["id"]},
        headers=ledger_headers(),
    )
    assert Decimal(balance.json()["balance"]) == Decimal(expected_balance)
    items = (await client.get(BASE + "/open-items", headers=ledger_headers())).json()["items"]
    assert any(Decimal(item["amount"]) == Decimal("1.18") for item in items)


async def evidence_case(
    client: httpx.AsyncClient, app: FastAPI
) -> tuple[dict[str, Any], dict[str, Any], Signer, str]:
    request, _, _, _ = await setup_charge(client, app, tax_treatment="EXTERNAL")
    row = await assessment(client, request)
    return request, row, Signer(app), await tax_group(client)


async def test_regression_v1_evidence_bypasses_regime_and_profile(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """Version-one evidence named no registration, so a composition company could post an
    IGST amount into a CGST account. Taxed version-one evidence is now refused."""
    request, row, signer, group = await evidence_case(client, app)
    cgst = await gst_account(client, group, "CGST", REGULAR)
    body = signer.body(
        computation(row, request["posting_date"], [("IGST", "0.18")], version=1),
        {"IGST": cgst["id"]},
    )
    response = await client.post(
        BASE + "/charge-tax-snapshots",
        json=body,
        headers=ledger_headers(registrations=[COMPOSITION]),
    )
    assert response.status_code == 422, response.text
    assert "version two" in response.text


async def test_evidence_registration_component_and_profile_rules(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    request, row, signer, group = await evidence_case(client, app)
    day = request["posting_date"]
    cgst = await gst_account(client, group, "CGST", REGULAR)
    sgst = await gst_account(client, group, "SGST", REGULAR)
    igst = await gst_account(client, group, "IGST", REGULAR)
    other_igst = await gst_account(client, group, "IGST", OTHER)
    tds = await withholding_account(client, group)
    intra = [("CGST", "0.09"), ("SGST", "0.09")]
    accounts = {"CGST": cgst["id"], "SGST": sgst["id"]}
    unknown = {"id": str(uuid7())}
    cases: list[tuple[dict[str, Any], str]] = [
        # Composition company with components.
        (signer.body(computation(row, day, intra, registration=COMPOSITION), accounts), "regime"),
        # Only a supplier-class registration charges.
        (signer.body(computation(row, day, intra, registration=ISD), accounts), SUPPLIER),
        (signer.body(computation(row, day, intra, registration=MISLABELED), accounts), SUPPLIER),
        # Registration gap: the registration ended before the posting date.
        (signer.body(computation(row, day, intra, registration=ENDED), accounts), "not valid"),
        # A registration absent from the signed Identity context.
        (signer.body(computation(row, day, intra, registration=unknown), accounts), "unavailable"),
        # Taxed version-two evidence must name a registration.
        (signer.body(computation(row, day, intra, registration=None), accounts), SCHEMA),
        # IGST into a CGST account.
        (signer.body(computation(row, day, [("IGST", "0.18")]), {"IGST": cgst["id"]}), PROFILE),
        # A withholding (wrong-profile) account.
        (signer.body(computation(row, day, [("IGST", "0.18")]), {"IGST": tds["id"]}), PROFILE),
        # The account's profile is bound to a different company registration.
        (
            signer.body(computation(row, day, [("IGST", "0.18")]), {"IGST": other_igst["id"]}),
            PROFILE,
        ),
        # Component sets are typed and restricted.
        (
            signer.body(
                computation(row, day, [("CGST", "0.09"), ("IGST", "0.09")]),
                {"CGST": cgst["id"], "IGST": igst["id"]},
            ),
            SCHEMA,
        ),
        (signer.body(computation(row, day, [("GST", "0.18")]), {"GST": igst["id"]}), SCHEMA),
        (signer.body(computation(row, day, [("SGST", "0.18")]), {"SGST": sgst["id"]}), SCHEMA),
    ]
    for body, message in cases:
        response = await client.post(
            BASE + "/charge-tax-snapshots", json=body, headers=evidence_headers()
        )
        assert response.status_code == 422, response.text
        assert message in response.text, response.text
    accepted = await client.post(
        BASE + "/charge-tax-snapshots",
        json=signer.body(computation(row, day, [("IGST", "0.18")]), {"IGST": igst["id"]}),
        headers=evidence_headers(),
    )
    assert accepted.status_code == 201, accepted.text


@pytest.mark.parametrize("version", [1, 2])
async def test_zero_component_evidence_needs_no_charging_regime(
    client: httpx.AsyncClient, app: FastAPI, version: int
) -> None:
    """A composition company's untaxed evidence is accepted, as is untaxed version one."""
    request, row, signer, _ = await evidence_case(client, app)
    body = signer.body(
        computation(row, request["posting_date"], [], registration=COMPOSITION, version=version),
        {},
    )
    response = await client.post(
        BASE + "/charge-tax-snapshots", json=body, headers=evidence_headers()
    )
    assert response.status_code == 201, response.text
    approved = await approve(client, row)
    assert approved.status_code == 200, approved.text

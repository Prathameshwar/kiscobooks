import secrets
import time
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.owner_snapshot import SnapshotCredential
from billing_platform.service_auth import (
    CompanyServiceScope,
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)
from pydantic import SecretStr

from tests.conftest import headers


async def test_broker_source_exports_only_active_company_broker_roles(client, app):
    from accounting.api.voucher_sources import facts
    from accounting.models.masters import Party, PartyRole

    tenant, company, another_company = uuid7(), uuid7(), uuid7()
    broker, customer = uuid7(), uuid7()
    initialized = await client.post(
        f"/v1/companies/{company}/accounting-setup/initialize", json={},
        headers=headers(tenant=tenant, company=company),
    )
    assert initialized.status_code == 200, initialized.text
    with tenant_scope(tenant):
        async with app.state.session_factory() as db, db.begin():
            for party_id, code, name in (
                (broker, "BROKER", "Broker agent"),
                (customer, "CUSTOMER", "Ordinary customer"),
            ):
                db.add(Party(
                    id=party_id, tenant_id=tenant, company_id=company, code=code,
                    name=name, legal_name=name, country_code="IN", status="ACTIVE",
                    row_version=1,
                ))
            await db.flush()
            for party_id, role in ((broker, "BROKER"), (customer, "CUSTOMER")):
                db.add(PartyRole(
                    id=uuid7(), tenant_id=tenant, company_id=company,
                    party_id=party_id, role=role, status="ACTIVE", row_version=1,
                ))
        async with app.state.session_factory() as db:
            bundle, after = await facts(db, tenant, company, "broker_party", None, 128)
            assert after is None
            assert len(bundle["masters"]) == 1
            assert bundle["masters"][0]["source_id"] == str(broker)
            assert bundle["masters"][0]["facts"]["name"] == "Broker agent"
            other, _ = await facts(db, tenant, another_company, "broker_party", None, 128)
            assert not other["masters"]


async def test_scoped_party_snapshot_does_not_export_private_names(client, app):
    from accounting.models.masters import Party

    tenant, company, party = uuid7(), uuid7(), uuid7()
    owner, entity = "accounting", "party"
    initialized = await client.post(
        f"/v1/companies/{company}/accounting-setup/initialize",
        json={},
        headers=headers(tenant=tenant, company=company),
    )
    assert initialized.status_code == 200, initialized.text
    with tenant_scope(tenant):
        async with app.state.session_factory() as db, db.begin():
            db.add(
                Party(
                    id=party,
                    tenant_id=tenant,
                    company_id=company,
                    code="P",
                    name="Private party",
                    legal_name="Private legal name",
                    country_code="IN",
                    status="ACTIVE",
                    row_version=1,
                )
            )
    secret = secrets.token_hex(32)
    key_id = "vouchers.snapshot.test"
    app.state.settings.voucher_snapshot_credentials[key_id] = SnapshotCredential(
        secret=SecretStr(secret),
        scopes=(CompanyServiceScope(tenant_id=tenant, company_id=company),),
    )
    path = f"/internal/v1/voucher-sources/{tenant}/{company}/{entity}"
    assert (await client.get(path)).status_code == 401
    framed = service_request_bytes(method="GET", path=path, query="limit=1", body=b"")
    stamp = int(time.time())
    key = ServiceKey("vouchers", owner, frozenset({"vouchers.snapshot.read"}), secret.encode())
    signature = sign_service_body(
        key, key_id=key_id, operation="vouchers.snapshot.read", timestamp=stamp, body=framed
    )
    request_headers = {
        "X-Source-Key-Id": key_id,
        "X-Source-Issued-At": str(stamp),
        "X-Source-Signature": signature,
    }
    response = await client.get(path + "?limit=1", headers=request_headers)
    assert response.status_code == 200, response.text
    verify_service_body(
        {
            key_id: ServiceKey(
                owner, "vouchers", frozenset({"vouchers.snapshot.response"}), secret.encode()
            )
        },
        key_id=key_id,
        issuer=owner,
        audience="vouchers",
        operation="vouchers.snapshot.response",
        timestamp=response.headers["x-source-issued-at"],
        signature=response.headers["x-source-signature"],
        body=service_response_bytes(request_bytes=framed, response_body=response.content),
        now=stamp,
    )
    assert (await client.get(path + "?limit=2", headers=request_headers)).status_code == 401
    assert (
        await client.get(
            path.replace(str(company), str(uuid.uuid4())) + "?limit=1", headers=request_headers
        )
    ).status_code == 401
    assert response.json()["bundle"]["masters"][0]["source_id"] == str(party)
    assert "Private" not in response.text


@pytest.mark.parametrize("open_start", [False, True])
async def test_master_lookup_is_signed_exact_and_company_scoped(client, app, open_start):
    import datetime as dt
    import json

    from accounting.models.masters import (
        Account,
        AccountGroup,
        AccountHead,
        Party,
        PartyTaxRegistration,
    )

    tenant, company, other = uuid7(), uuid7(), uuid7()
    supplier, gst_party = uuid7(), uuid7()
    for target in (company, other):
        initialized = await client.post(
            f"/v1/companies/{target}/accounting-setup/initialize",
            json={},
            headers=headers(tenant=tenant, company=target),
        )
        assert initialized.status_code == 200, initialized.text
    with tenant_scope(tenant):
        async with app.state.session_factory() as db, db.begin():
            head, group = uuid7(), uuid7()
            db.add(AccountHead(
                id=head, tenant_id=tenant, company_id=company, code="LOOKUP-HEAD",
                name="Head", nature="LIABILITY", row_version=1,
            ))
            await db.flush()
            db.add(AccountGroup(
                id=group, tenant_id=tenant, company_id=company, code="LOOKUP-GROUP",
                name="Group", head_id=head, status="ACTIVE", row_version=1,
            ))
            await db.flush()
            for party_id, code, target in (
                (supplier, "SUP-1", company),
                (gst_party, "SUP-2", company),
                (uuid7(), "SUP-1", other),
            ):
                db.add(Party(
                    id=party_id, tenant_id=tenant, company_id=target, code=code,
                    name="Private " + code, legal_name="Private", country_code="IN",
                    status="ACTIVE", row_version=3,
                ))
            await db.flush()
            db.add(PartyTaxRegistration(
                id=uuid7(), tenant_id=tenant, company_id=company, party_id=gst_party,
                scheme="GST_IN", registration_type="REGULAR",
                registration_number="27ABCDE1234F1Z5", country_code="IN", state_code="MH",
                valid_from=None if open_start else dt.date(2020, 4, 1),
                row_version=1,
            ))
            for account_id, code, kind, party in (
                (uuid7(), "SUP-1-LEDGER", "PARTY", supplier),
                (uuid7(), "SUP-2-LEDGER", "PARTY", gst_party),
                (uuid7(), "EXP-RENT", "GENERAL", None),
            ):
                db.add(Account(
                    id=account_id, tenant_id=tenant, company_id=company, code=code,
                    name="Private ledger", group_id=group, kind=kind, party_id=party,
                    party_role="SUPPLIER" if party else None, currency_mode="BASE",
                    status="ACTIVE", row_version=2,
                ))
    secret = secrets.token_hex(32)
    key_id = "vouchers.lookup.test"
    app.state.settings.voucher_snapshot_credentials[key_id] = SnapshotCredential(
        secret=SecretStr(secret),
        scopes=(CompanyServiceScope(tenant_id=tenant, company_id=company),),
    )
    path = f"/internal/v1/voucher-lookups/{tenant}/{company}"
    body = json.dumps({
        "party_codes": ["SUP-1", "MISSING"],
        "party_gstins": ["27ABCDE1234F1Z5"],
        "account_codes": ["EXP-RENT", "sup-1-ledger"],
    }).encode()

    def signed(payload: bytes, target: str = path) -> dict[str, str]:
        framed = service_request_bytes(method="POST", path=target, query="", body=payload)
        stamp = int(time.time())
        key = ServiceKey(
            "vouchers", "accounting", frozenset({"vouchers.snapshot.read"}), secret.encode()
        )
        return {
            "X-Source-Key-Id": key_id,
            "X-Source-Issued-At": str(stamp),
            "X-Source-Signature": sign_service_body(
                key, key_id=key_id, operation="vouchers.snapshot.read", timestamp=stamp,
                body=framed,
            ),
            "Content-Type": "application/json",
        }

    assert (await client.post(path, content=body)).status_code == 401
    tampered = await client.post(
        path, content=body.replace(b"SUP-1", b"SUP-2"), headers=signed(body)
    )
    assert tampered.status_code == 401
    elsewhere = path.replace(str(company), str(other))
    foreign = await client.post(elsewhere, content=body, headers=signed(body, elsewhere))
    assert foreign.status_code == 401
    response = await client.post(path, content=body, headers=signed(body))
    assert response.status_code == 200, response.text
    assert "Private" not in response.text
    data = response.json()
    assert {row["code"] for row in data["parties"]} == {"SUP-1", "SUP-2"}
    assert all(row["source_version"] == 3 for row in data["parties"])
    assert data["registrations"][0]["party_id"] == str(gst_party)
    assert data["registrations"][0]["valid_from"] == (None if open_start else "2020-04-01")
    assert {row["code"] for row in data["party_accounts"]} == {"SUP-1-LEDGER", "SUP-2-LEDGER"}
    assert [row["code"] for row in data["accounts"]] == ["EXP-RENT"]
    invalid = json.dumps({"party_codes": ["X"], "extra": True}).encode()
    assert (await client.post(path, content=invalid, headers=signed(invalid))).status_code == 422


async def test_automatic_voucher_source_requires_native_accounting_company(client, app):
    from billing_platform.owner_snapshot import request_headers
    from tests.conftest import TENANT, COMPANY
    secret, key_id = secrets.token_hex(32), "vouchers.enrollment.test"
    app.state.settings.voucher_snapshot_credentials[key_id] = SnapshotCredential(secret=SecretStr(secret), allow_enrolled_companies=True)
    def signed(company):
        path = f"/internal/v1/voucher-sources/{TENANT}/{company}/account"
        framed = service_request_bytes(method="GET", path=path, query="", body=b"")
        return path, request_headers(requester="vouchers", owner="accounting", key_id=key_id, secret=secret.encode(), framed=framed)
    path, auth = signed(COMPANY)
    assert (await client.get(path, headers=auth)).status_code == 401
    initialized = await client.post(f"/v1/companies/{COMPANY}/accounting-setup/initialize", json={}, headers=headers())
    assert initialized.status_code == 200, initialized.text
    path, auth = signed(COMPANY)
    response = await client.get(path, headers=auth)
    assert response.status_code == 200, response.text
    assert response.json()["bundle"]["company_id"] == str(COMPANY)
    path, auth = signed(uuid7())
    assert (await client.get(path, headers=auth)).status_code == 401

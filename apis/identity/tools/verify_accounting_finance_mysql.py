"""Real Identity/Accounting contracts on two validated disposable loopback MySQL schemas."""

import asyncio
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, cast

import httpx
from accounting.config import Settings as AccountingSettings
from accounting.main import create_app as accounting_app
from accounting.tasks.posting_delivery import deliver
from alembic import command
from alembic.config import Config
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.permissions import PERMISSIONS
from identity_posting import PostingClient
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from identity.config import CatalogSourceCredential, CatalogSourceScope
from identity.config import Settings as IdentitySettings
from identity.main import create_app as identity_app
from identity.models import Company, CompanyFeature, PostingReservation
from tests.factories import build_user, seed_two_companies

ROOT = Path(__file__).resolve().parents[3]
SERVER = "mysql+asyncmy://root@127.0.0.1:13396"


async def schema(name: str, *, create: bool) -> None:
    if not re.fullmatch(r"(?:accounting|identity_finance)_test_[0-9a-f]{32}", name):
        raise ValueError("only this tool's disposable schema names are accepted")
    engine = create_async_engine(SERVER, poolclass=NullPool)
    try:
        async with engine.connect() as db:
            await db.execute(
                text(
                    f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    if create
                    else f"DROP DATABASE `{name}`"
                )
            )
    finally:
        await engine.dispose()


def migration(service: str, name: str) -> Config:
    config = Config(str(ROOT / "dbs" / service / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "dbs" / service))
    config.set_main_option("sqlalchemy.url", SERVER + "/" + name)
    return config


async def scenario(identity_name: str, accounting_name: str) -> None:
    secret, request_secret, response_secret = [secrets.token_hex(32) for _ in range(3)]
    identity = identity_app(
        IdentitySettings(
            database_url=SERVER + "/" + identity_name,
            actor_signing_secret=SecretStr(secret),
            cursor_signing_secret=SecretStr(secrets.token_hex(32)),
            public_auth_url="https://auth.test",
        )
    )
    accounting = accounting_app(
        AccountingSettings(
            database_url=SERVER + "/" + accounting_name, actor_signing_secret=SecretStr(secret)
        )
    )
    tenant, other, admin, approver = [uuid7() for _ in range(4)]
    try:
        async with identity.state.session_factory() as db:
            company, _ = await seed_two_companies(db, tenant, other)
            with tenant_scope(tenant):
                db.add_all(
                    [
                        build_user(tenant_id=tenant, user_id=user, email=f"{user}@example.test")
                        for user in (admin, approver)
                    ]
                )
                db.add(
                    CompanyFeature(
                        id=uuid7(),
                        tenant_id=tenant,
                        company_id=company,
                        feature_key="credit_limits",
                        is_enabled=True,
                    )
                )
                await db.commit()
        identity.state.settings.accounting_reservation_credentials = {
            "accounting.test": CatalogSourceCredential(
                secret=SecretStr(request_secret),
                scopes=(CatalogSourceScope(tenant_id=tenant, company_id=company),),
            )
        }
        identity.state.settings.accounting_reservation_response_secret = SecretStr(response_secret)

        def actor(user: uuid.UUID) -> dict[str, str]:
            raw = json.dumps(
                {
                    "issued_at": int(time.time()),
                    "tenant_id": str(tenant),
                    "user_id": str(user),
                    "grants": [
                        {
                            "permissions": sorted(PERMISSIONS),
                            "scope_type": "tenant",
                            "scope_id": None,
                            "valid_from": "2020-01-01",
                        }
                    ],
                },
                separators=(",", ":"),
            ).encode()
            return {
                "X-Actor-Context": base64.urlsafe_b64encode(raw).decode().rstrip("="),
                "X-Actor-Signature": hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(),
            }

        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=identity), base_url="https://identity.test"
            ) as id_http,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=accounting), base_url="https://accounting.test"
            ) as ac_http,
        ):
            authority = PostingClient(
                id_http,
                key_id="accounting.test",
                request_secret=request_secret.encode(),
                response_keys={"current": response_secret.encode()},
                issuer="accounting",
            )
            accounting.state.posting_client = authority
            base = f"/v1/companies/{company}"

            async def headers(user: uuid.UUID = admin) -> dict[str, str]:
                result = await id_http.get(
                    "/internal/v1/gateway/authorize",
                    headers=actor(user) | {"X-Original-URI": "/accounting" + base + "/parties"},
                )
                assert result.status_code == 204, result.text
                return {
                    key: result.headers[key]
                    for key in (
                        "X-Actor-Context",
                        "X-Actor-Signature",
                        "X-Company-Context",
                        "X-Company-Signature",
                    )
                } | {"Idempotency-Key": str(uuid7())}

            async def post(
                path: str, body: dict[str, Any], *, user: uuid.UUID = admin
            ) -> dict[str, Any]:
                result = await ac_http.post(base + path, json=body, headers=await headers(user))
                assert result.status_code in {200, 201}, (path, result.text)
                return cast(dict[str, Any], result.json())

            async def get(path: str) -> dict[str, Any]:
                result = await ac_http.get(base + path, headers=await headers())
                assert result.status_code == 200, (path, result.text)
                return cast(dict[str, Any], result.json())

            async def post_journal(identifier: str) -> dict[str, Any]:
                row = await get("/journals/" + identifier)
                return await post(
                    f"/journals/{identifier}/post", {"expected_version": row["row_version"]}
                )

            await post("/accounting-setup/initialize", {})
            await post("/accounting-setup/install", {"business_accounts": True})
            await post("/financial-setup/initialize", {})
            await post("/fiscal-years/generate", {"start_year": 2026})
            period = (await get("/fiscal-periods"))["items"][0]
            await post(
                f"/fiscal-periods/{period['id']}/transition",
                {"expected_version": 1, "status": "OPEN", "reason": "Initial period"},
            )
            opening = await post(
                "/opening-batches",
                {"posting_date": "2026-04-01", "description": "Zero initial balances"},
            )
            await post(f"/opening-batches/{opening['id']}/finalize-zero", {"expected_version": 1})
            party = await post(
                "/parties",
                {
                    "code": "FINANCE",
                    "name": "Finance bridge",
                    "legal_name": "Finance bridge",
                    "country_code": "IN",
                },
            )
            await post(f"/parties/{party['id']}/activate", {"expected_version": 1})
            role = await post("/party-roles", {"party_id": party["id"], "role": "CUSTOMER"})
            await post(f"/party-roles/{role['id']}/activate", {"expected_version": 1})
            groups = {row["code"]: row for row in (await get("/account-groups?limit=200"))["items"]}
            account = await post(
                "/accounts",
                {
                    "code": "CUSTOMER",
                    "name": "Bridge debtor",
                    "kind": "PARTY",
                    "group_id": groups["DEBTORS"]["id"],
                    "party_id": party["id"],
                    "party_role": "CUSTOMER",
                },
            )
            await post(f"/accounts/{account['id']}/activate", {"expected_version": 1})
            accounts = (await get("/accounts?limit=200"))["items"]
            cash = next(row for row in accounts if row["kind"] == "CASH")
            revenue = next(row for row in accounts if row["kind"] == "GENERAL")
            common = {
                "account_id": account["id"],
                "currency": "INR",
                "amount": "100",
                "exchange_rate": "1",
                "document_date": "2026-04-02",
                "posting_date": "2026-04-02",
                "reference": "BRIDGE",
                "description": "Native source",
                "source_system": "billing",
                "source_type": "invoice",
                "source_id": str(uuid7()),
            }
            invoice = await post(
                "/source-documents",
                common
                | {
                    "kind": "INVOICE",
                    "counterpart_account_id": revenue["id"],
                    "due_date": "2026-04-02",
                },
            )
            await post_journal(invoice["journal_id"])
            with tenant_scope(tenant):
                async with identity.state.session_factory() as db:
                    pending = await db.scalar(
                        select(PostingReservation).where(
                            PostingReservation.operation_id == uuid.UUID(invoice["journal_id"])
                        )
                    )
                    assert (
                        pending is not None
                        and pending.owner_service == "accounting"
                        and pending.status == "pending"
                    )
                    owner = await db.get(Company, company)
                    assert owner is not None and owner.first_posted_at is None
            assert (await deliver(accounting.state.session_factory, authority)).confirmed == 1
            with tenant_scope(tenant):
                async with identity.state.session_factory() as db:
                    owner = await db.get(Company, company)
                    assert owner is not None and owner.first_posted_at is not None
            receipt = await post(
                "/source-documents",
                common
                | {
                    "kind": "RECEIPT",
                    "counterpart_account_id": cash["id"],
                    "amount": "40",
                    "document_date": "2026-04-08",
                    "posting_date": "2026-04-08",
                    "source_type": "receipt",
                    "source_id": str(uuid7()),
                },
            )
            await post_journal(receipt["journal_id"])
            items = (await get("/open-items"))["items"]
            debt = next(item for item in items if item["direction"] == "DEBT")
            credit = next(item for item in items if item["direction"] == "CREDIT")
            await post(
                "/allocations",
                {
                    "debt_item_id": debt["id"],
                    "credit_item_id": credit["id"],
                    "amount": "40",
                    "posting_date": "2026-04-08",
                },
            )
            policy = await post(
                "/charge-policies",
                {
                    "account_id": account["id"],
                    "offset_account_id": revenue["id"],
                    "currency": "INR",
                    "valid_from": "2026-04-01",
                    "accrual_start_date": "2026-04-01",
                    "method": "INTEREST",
                    "rate": "36.5",
                    "tax_treatment": "NON_TAXABLE",
                    "tax_reason": "Fixture exemption",
                },
            )
            charge = await post(
                "/charge-assessments",
                {
                    "item_id": debt["id"],
                    "policy_id": policy["id"],
                    "coverage_end_date": "2026-04-13",
                    "posting_date": "2026-04-13",
                    "due_date": "2026-04-20",
                    "exchange_rate": "1",
                },
            )
            approved = await post(
                f"/charge-assessments/{charge['id']}/approve",
                {"expected_version": 1, "reason": "Independent review"},
                user=approver,
            )
            await post_journal(approved["journal_id"])
            assert (await deliver(accounting.state.session_factory, authority)).confirmed == 2
            reconciliation = await get(
                f"/subledger/reconciliation?account_id={account['id']}&currency=INR&as_of=2026-04-30"
            )
            assert reconciliation["difference"] == "0.0000", reconciliation
            print(
                "Native Identity gateway and Accounting opening/source/allocation/charge "
                "with Identity confirmation passed"
            )
    finally:
        await identity.state.engine.dispose()
        await accounting.state.engine.dispose()


async def clear_accounting_reservations(name: str) -> None:
    if not re.fullmatch(r"identity_finance_test_[0-9a-f]{32}", name):
        raise ValueError("refusing a non-test schema")
    engine = create_async_engine(SERVER + "/" + name, poolclass=NullPool)
    try:
        async with engine.begin() as db:
            assert await db.scalar(text("SELECT DATABASE()")) == name
            await db.execute(
                text("DELETE FROM posting_reservation WHERE owner_service = :owner"),
                {"owner": "accounting"},
            )
    finally:
        await engine.dispose()


def main() -> None:
    names = ("identity_finance_test_" + uuid.uuid4().hex, "accounting_test_" + uuid.uuid4().hex)
    created = []
    try:
        for name in names:
            asyncio.run(schema(name, create=True))
            created.append(name)
        identity_config, accounting_config = (
            migration(service, name)
            for service, name in zip(("identity", "accounting"), names, strict=True)
        )
        command.upgrade(identity_config, "0059")
        command.upgrade(accounting_config, "head")
        asyncio.run(scenario(*names))
        try:
            command.downgrade(identity_config, "0058")
        except RuntimeError as exc:
            assert "retain Accounting reservation ownership" in str(exc)
        else:
            raise AssertionError("unsafe Identity ownership downgrade was not rejected")
        asyncio.run(clear_accounting_reservations(names[0]))
        command.downgrade(identity_config, "0058")
        command.upgrade(identity_config, "0059")
        print("Identity 0059 upgrade and safe/unsafe downgrade checks passed")
    finally:
        for name in reversed(created):
            asyncio.run(schema(name, create=False))


if __name__ == "__main__":
    main()

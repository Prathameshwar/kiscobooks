"""Exercise Identity policy APIs, its signed gateway and Accounting as independent apps."""

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from typing import Any, cast

import httpx
from accounting.config import Settings as AccountingSettings
from accounting.main import create_app as accounting_app
from accounting.metadata import service_metadata
from billing_platform.db import Base, tenant_scope
from pydantic import SecretStr

from identity.config import Settings as IdentitySettings
from identity.main import create_app as identity_app
from tests.factories import build_user, seed_two_companies


async def main() -> None:
    secret = secrets.token_hex(32)
    identity = identity_app(
        IdentitySettings(
            database_url="sqlite+aiosqlite:///:memory:",
            actor_signing_secret=SecretStr(secret),
            cursor_signing_secret=SecretStr(secrets.token_hex(32)),
            public_auth_url="https://auth.test",
        )
    )
    accounting = accounting_app(
        AccountingSettings(
            database_url="sqlite+aiosqlite:///:memory:", actor_signing_secret=SecretStr(secret)
        )
    )
    tenant, other, admin, reader = [uuid.uuid4() for _ in range(4)]
    try:
        async with identity.state.engine.begin() as db:
            await db.run_sync(Base.metadata.create_all)
        async with accounting.state.engine.begin() as db:
            await db.run_sync(service_metadata().create_all)
        async with identity.state.session_factory() as db:
            company, _ = await seed_two_companies(db, tenant, other)
            with tenant_scope(tenant):
                db.add_all(
                    [
                        build_user(tenant_id=tenant, user_id=user, email=f"{user}@example.test")
                        for user in (admin, reader)
                    ]
                )
                await db.commit()
        permissions = [
            "field_policy.manage",
            "field_config.manage",
            "accounting.party.read",
            "accounting.party.manage",
            "accounting.setup.read",
            "accounting.setup.manage",
            "accounting.history.read",
            "accounting.export.read",
        ]

        def actor(user: uuid.UUID) -> dict[str, str]:
            value = json.dumps(
                {
                    "issued_at": int(time.time()),
                    "tenant_id": str(tenant),
                    "user_id": str(user),
                    "grants": [
                        {
                            "permissions": permissions,
                            "scope_type": "tenant",
                            "scope_id": None,
                            "valid_from": "2020-01-01",
                        }
                    ],
                },
                separators=(",", ":"),
            ).encode()
            return {
                "X-Actor-Context": base64.urlsafe_b64encode(value).decode().rstrip("="),
                "X-Actor-Signature": hmac.new(secret.encode(), value, hashlib.sha256).hexdigest(),
            }

        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=identity), base_url="http://identity.test"
            ) as id_http,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=accounting), base_url="http://accounting.test"
            ) as ac_http,
        ):
            base = f"/v1/companies/{company}"

            async def gateway(user: uuid.UUID) -> dict[str, str]:
                response = await id_http.get(
                    "/internal/v1/gateway/authorize",
                    headers=actor(user) | {"X-Original-URI": "/accounting" + base + "/parties"},
                )
                assert response.status_code == 204, response.text
                return {
                    name: response.headers[name]
                    for name in (
                        "X-Actor-Context",
                        "X-Actor-Signature",
                        "X-Company-Context",
                        "X-Company-Signature",
                    )
                }

            async def post(path: str, body: dict[str, Any]) -> dict[str, Any]:
                response = await ac_http.post(
                    base + path,
                    json=body,
                    headers=(await gateway(admin)) | {"Idempotency-Key": str(uuid.uuid4())},
                )
                assert response.status_code in (200, 201), response.text
                return cast(dict[str, Any], response.json())

            await post("/accounting-setup/initialize", {})
            row = await post(
                "/parties",
                {
                    "code": "BRIDGE",
                    "name": "Bridge",
                    "legal_name": "Bridge",
                    "country_code": "IN",
                    "notes": "Private note",
                },
            )
            row = await post(
                f'/parties/{row["id"]}/activate', {"expected_version": row["row_version"]}
            )
            policies = []
            for access in ("read", "write"):
                body = {
                    "entity_type": "accounting.party",
                    "subject_type": "user",
                    "subject_id": str(reader),
                    "field_key": "notes",
                    "access": access,
                    "effect": "deny",
                    "reason": "Integration",
                    "scope_type": "company",
                    "scope_id": str(company),
                    "condition": {"field": "status", "cmp": "eq", "value": "ACTIVE"},
                }
                response = await id_http.post("/v1/field-policies", headers=actor(admin), json=body)
                assert response.status_code == 201, response.text
                policies.append((response.json()["id"], body))
            response = await id_http.put(
                "/v1/entities/accounting.party/field-config/notes",
                headers=actor(admin),
                json={"label_override": "Private note", "is_visible": False},
            )
            assert response.status_code == 200, response.text
            reader_headers = await gateway(reader)
            detail = await ac_http.get(base + f'/parties/{row["id"]}', headers=reader_headers)
            assert detail.status_code == 200 and "notes" not in detail.json(), detail.text
            history = await ac_http.get(
                base + f'/history/parties/{row["id"]}', headers=reader_headers
            )
            assert history.status_code == 200, history.text
            assert all(
                "notes" not in revision["changed_fields"] for revision in history.json()["items"]
            )
            exported = await ac_http.get(base + "/exports/parties", headers=reader_headers)
            assert (
                exported.status_code == 200 and "notes" not in exported.json()["items"][0]
            ), exported.text
            denied = await ac_http.patch(
                base + f'/parties/{row["id"]}',
                headers=reader_headers | {"Idempotency-Key": str(uuid.uuid4())},
                json={"expected_version": row["row_version"], "notes": "Forbidden"},
            )
            assert denied.status_code == 403, denied.text
            for pid, body in policies:
                response = await id_http.put(
                    f"/v1/field-policies/{pid}",
                    headers=actor(admin),
                    json=body | {"is_active": False},
                )
                assert response.status_code == 200, response.text
            restored = await ac_http.get(
                base + f'/parties/{row["id"]}', headers=await gateway(reader)
            )
            assert restored.json()["notes"] == "Private note", restored.text
            assert restored.json()["row_version"] == row["row_version"]
            forged = await ac_http.get(
                base + f'/parties/{row["id"]}',
                headers=reader_headers | {"X-Company-Signature": "0" * 64},
            )
            assert forged.status_code == 401, forged.text
            print("PASS: Identity policy/layout, signed context, Accounting reads and revocation")
    finally:
        await identity.state.engine.dispose()
        await accounting.state.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

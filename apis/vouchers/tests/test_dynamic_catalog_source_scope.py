"""Fresh product source delivery is limited to an already enrolled company."""

import secrets
import time

from billing_platform.db import tenant_scope
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.service_auth import ServiceKey, service_request_bytes, sign_service_body
from conftest import COMPANY, TENANT
from pydantic import SecretStr, ValidationError

from vouchers.config import SourceCredential
from vouchers.models import core as m


async def send(client, app, company):
    key_id = "catalog.dynamic.test"
    secret = secrets.token_hex(32)
    app.state.settings.source_credentials[key_id] = SourceCredential(
        issuer="catalog",
        secret=SecretStr(secret),
        allow_enrolled_companies=True,
    )
    payload = {
        "message_id": str(uuid7()),
        "tenant_id": str(TENANT),
        "company_id": str(company),
        "definitions": [],
        "masters": [],
    }
    raw = canonical_json(payload)
    stamp = int(time.time())
    return await client.post(
        "/internal/v1/sources",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Service-Key-Id": key_id,
            "X-Service-Issuer": "catalog",
            "X-Service-Timestamp": str(stamp),
            "X-Service-Signature": sign_service_body(
                ServiceKey(
                    "catalog", "vouchers", frozenset({"vouchers.sources.apply"}), secret.encode()
                ),
                key_id=key_id,
                operation="vouchers.sources.apply",
                timestamp=stamp,
                body=service_request_bytes(
                    method="POST", path="/internal/v1/sources", query="", body=raw
                ),
            ),
        },
    )


async def test_dynamic_catalog_source_requires_identity_company_evidence(client, app):
    assert (await send(client, app, COMPANY)).status_code == 401
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            db.add(
                m.VoucherMasterEvidence(
                    id=uuid7(),
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    owner="identity",
                    entity_type="company",
                    source_id=COMPANY,
                    source_version=1,
                    status="ACTIVE",
                    facts={},
                    content_hash="0" * 64,
                )
            )
    assert (await send(client, app, COMPANY)).status_code == 200
    assert (await send(client, app, uuid7())).status_code == 401


def test_only_catalog_can_use_dynamic_source_scope():
    try:
        SourceCredential(
            issuer="accounting", secret=SecretStr("x" * 32), allow_enrolled_companies=True
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Accounting must not gain a dynamic source grant")

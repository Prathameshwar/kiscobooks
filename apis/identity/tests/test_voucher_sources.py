import secrets
import time
import uuid

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

from identity.domain.voucher_fields import native_field


def test_phase5_native_voucher_fields_are_available_to_identity_policy() -> None:
    assert native_field("vouchers.voucher", "fulfillment_terms") is not None
    assert native_field("vouchers.voucher_item", "planned_quantity") is not None


async def test_identity_supports_both_voucher_definition_entities_and_signed_owner_export(
    client, app, session, tenant_a, tenant_b
):
    from tests.api_support import actor_headers, grant
    from tests.factories import seed_two_companies

    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    tenant = tenant_a
    owner, entity = "identity", "vouchers.voucher"
    for name in ("vouchers.voucher", "vouchers.voucher_item"):
        auth = actor_headers(
            tenant_id=tenant, user_id=uuid7(), grants=[grant(["custom_field.manage"])]
        )
        created = await client.post(
            "/v1/custom-field-definitions",
            headers=auth,
            json={
                "entity_type": name,
                "company_id": str(company),
                "label": "Voucher note",
                "definition": {"key": "cf_note", "data_type": "text"},
            },
        )
        assert created.status_code == 201, created.text
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
    assert response.json()["bundle"]["definitions"][0]["definition"]["key"] == "cf_note"

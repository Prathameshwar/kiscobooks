"""Renderer resolution is signed, scoped and falls back only to shipped standard."""

import json
import secrets
import time

from billing_platform.ids import uuid7
from billing_platform.service_auth import (
    CompanyServiceScope,
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)
from pydantic import SecretStr

from design.config import PrintSource
from tests.conftest import make_template, publish_template


async def test_renderer_resolution_signed_scope_standard_and_matching_rule(
    client, app, tenant_id, company_id, auth_headers
):
    secret = secrets.token_bytes(32).hex().encode()
    app.state.settings.print_source = PrintSource(
        secret=SecretStr(secret.decode()),
        scopes=[CompanyServiceScope(tenant_id=tenant_id, company_id=company_id)],
    )
    path = "/internal/v1/print-layout"
    body = {
        "tenant_id": str(tenant_id),
        "company_id": str(company_id),
        "voucher_kind": "PURCHASE",
        "voucher_type_id": str(uuid7()),
        "currency_code": "INR",
    }

    async def resolve(payload, *, sign=True):
        raw = json.dumps(payload, separators=(",", ":")).encode()
        framed = service_request_bytes(method="POST", path=path, query="", body=raw)
        stamp = int(time.time())
        auth = {"Content-Type": "application/json"}
        if sign:
            auth.update(
                {
                    "X-Source-Key-Id": "current",
                    "X-Source-Issued-At": str(stamp),
                    "X-Source-Signature": sign_service_body(
                        ServiceKey(
                            "vouchers", "design", frozenset({"design.print.resolve"}), secret
                        ),
                        key_id="current",
                        operation="design.print.resolve",
                        timestamp=stamp,
                        body=framed,
                    ),
                }
            )
        result = await client.post(path, content=raw, headers=auth)
        if result.status_code == 200:
            verify_service_body(
                {
                    "current": ServiceKey(
                        "design", "vouchers", frozenset({"design.print.resolve"}), secret
                    )
                },
                key_id=result.headers["x-source-key-id"],
                issuer="design",
                audience="vouchers",
                operation="design.print.resolve",
                timestamp=result.headers["x-source-issued-at"],
                signature=result.headers["x-source-signature"],
                body=service_response_bytes(request_bytes=framed, response_body=result.content),
                now=stamp,
                maximum_age=30,
            )
        return result

    assert (await resolve(body, sign=False)).status_code == 401
    assert (await resolve(body | {"company_id": str(uuid7())})).status_code == 403
    assert (await resolve(body | {"tenant_id": str(uuid7())})).status_code == 403
    standard = await resolve(body)
    assert standard.status_code == 200, standard.text
    assert standard.json()["source"] == "BUILTIN"
    # The standard layout's version is frozen into every print job; Vouchers refuses any other.
    import hashlib

    assert standard.json()["version"] == "purchase-a4@7"
    assert standard.json()["layout_digest"] == hashlib.sha256(b"purchase-a4@7").hexdigest()
    # Publishing a layout alone does not make it a Purchase fallback.
    template = await make_template(client, company_id, auth_headers)
    await publish_template(client, company_id, auth_headers, template)
    assert (await resolve(body)).json()["source"] == "BUILTIN"
    rule = await client.post(
        f"/v1/companies/{company_id}/assignments",
        headers=auth_headers,
        json={"voucher_kind": "PURCHASE", "template_id": template["id"]},
    )
    assert rule.status_code == 201, rule.text
    custom = await resolve(body)
    assert custom.status_code == 200, custom.text
    assert custom.json()["source"] == "CUSTOM"
    assert custom.json()["template_id"] == template["id"]
    assert custom.json()["layout_definition"]["sections"][0]["elements"][0]["x"] == 10.0

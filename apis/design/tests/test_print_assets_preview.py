"""Print resolution carries a layout's images and serves previews (designer plan §8 R2/R4).

The renderer never fetches a picture: the signed resolution carries the verified bytes of the
images a layout names, or the reason one cannot print. A preview resolves one saved version
of a template the company may print with, published or not, and says it is a preview.
"""

import base64
import hashlib
import json
import secrets
import time
import uuid
from pathlib import Path

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.service_auth import (
    CompanyServiceScope,
    ServiceKey,
    service_request_bytes,
    sign_service_body,
)
from fastapi import FastAPI
from pydantic import SecretStr

from design.config import PrintSource
from design.models.template import InvoiceTemplateAsset
from design.schemas.printing import PRINT_IMAGE_MAX_BYTES
from tests.conftest import canvas, make_template, publish_template
from tests.test_assets_components import LOGO, png, register

PATH = "/internal/v1/print-layout"
OPERATION = "design.print.resolve"


def resolver(client: httpx.AsyncClient, app: FastAPI, tenant: uuid.UUID, company: uuid.UUID):
    secret = secrets.token_bytes(32).hex().encode()
    app.state.settings.print_source = PrintSource(
        secret=SecretStr(secret.decode()),
        scopes=[CompanyServiceScope(tenant_id=tenant, company_id=company)],
    )
    body = {
        "tenant_id": str(tenant),
        "company_id": str(company),
        "voucher_kind": "PURCHASE",
        "voucher_type_id": str(uuid7()),
        "currency_code": "INR",
    }

    async def resolve(**changes: object) -> httpx.Response:
        raw = json.dumps(body | changes, separators=(",", ":")).encode()
        framed = service_request_bytes(method="POST", path=PATH, query="", body=raw)
        stamp = int(time.time())
        key = ServiceKey("vouchers", "design", frozenset({OPERATION}), secret)
        return await client.post(
            PATH,
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Source-Key-Id": "current",
                "X-Source-Issued-At": str(stamp),
                "X-Source-Signature": sign_service_body(
                    key, key_id="current", operation=OPERATION, timestamp=stamp, body=framed
                ),
            },
        )

    return resolve


async def routed(client, company, auth, layout):
    template = await make_template(client, company, auth, code="img-" + uuid7().hex[:8])
    version = await client.post(
        f"/v1/companies/{company}/templates/{template['id']}/versions",
        json={"layout_definition": layout},
        headers=auth,
    )
    assert version.status_code == 201, version.text
    await publish_template(client, company, auth, template, version.json()["id"])
    rule = await client.post(
        f"/v1/companies/{company}/assignments",
        headers=auth,
        json={"voucher_kind": "PURCHASE", "template_id": template["id"]},
    )
    assert rule.status_code == 201, rule.text
    return template, version.json()


async def test_a_routed_layouts_image_arrives_with_its_verified_bytes(
    client, app, tenant_id, company_id, auth_headers, tmp_path: Path
):
    asset = (await register(client, company_id, auth_headers, app, tmp_path)).json()
    await routed(client, company_id, auth_headers, canvas(asset_id=asset["id"]))
    result = await resolver(client, app, tenant_id, company_id)()
    assert result.status_code == 200, result.text
    [image] = result.json()["assets"]
    assert image["status"] == "READY" and image["asset_id"] == asset["id"]
    assert base64.b64decode(image["content_base64"]) == LOGO
    assert image["sha256"] == hashlib.sha256(LOGO).hexdigest()
    assert image["mime_type"] == "image/png"


async def test_a_withdrawn_oversized_or_tampered_image_comes_with_its_reason_not_its_bytes(
    client, app, tenant_id, company_id, auth_headers, tmp_path: Path
):
    asset = (await register(client, company_id, auth_headers, app, tmp_path)).json()
    await routed(client, company_id, auth_headers, canvas(asset_id=asset["id"]))
    resolve = resolver(client, app, tenant_id, company_id)
    identity = uuid.UUID(asset["id"])

    async def status() -> str:
        result = await resolve()
        assert result.status_code == 200, result.text
        [image] = result.json()["assets"]
        assert (image["content_base64"] is not None) == (image["status"] == "READY")
        return str(image["status"])

    async def change(**values: object) -> None:
        with tenant_scope(tenant_id):
            async with app.state.session_factory() as db, db.begin():
                row = await db.get(InvoiceTemplateAsset, identity)
                for key, value in values.items():
                    setattr(row, key, value)

    await change(file_size_bytes=PRINT_IMAGE_MAX_BYTES + 1)
    assert await status() == "TOO_LARGE"
    await change(file_size_bytes=len(LOGO), content_digest="0" * 64)
    assert await status() == "UNAVAILABLE"  # the stored bytes no longer match their digest
    await change(content_digest=hashlib.sha256(LOGO).hexdigest(), is_active=False)
    assert await status() == "WITHDRAWN"
    await change(is_active=True)
    assert await status() == "READY"


async def test_images_over_the_layouts_budget_are_named_not_sent(
    client, app, tenant_id, company_id, auth_headers, tmp_path: Path
):
    big = base64.b64encode(png(320, 320, noisy=True)).decode()  # about 300 KiB each
    ids = []
    for _ in range(3):
        uploaded = await register(
            client, company_id, auth_headers, app, tmp_path, content_base64=big
        )
        assert uploaded.status_code == 201, uploaded.text
        ids.append(uploaded.json()["id"])
    layout = canvas(asset_id=ids[0])
    elements = layout["sections"][0]["elements"]  # type: ignore[index]
    for index, identity in enumerate(ids[1:], 2):
        elements.append(elements[0] | {"id": f"el_logo_{index}", "asset_id": identity})
    await routed(client, company_id, auth_headers, layout)
    result = await resolver(client, app, tenant_id, company_id)()
    assert result.status_code == 200, result.text
    assert [row["status"] for row in result.json()["assets"]] == ["READY", "READY", "OVER_BUDGET"]


async def test_another_companys_asset_never_arrives_even_if_a_layout_names_it(
    client, app, tenant_id, company_id, signed_headers, auth_headers, tmp_path: Path
):
    other = uuid7()
    theirs = (await register(client, other, signed_headers(tenant_id, other), app, tmp_path)).json()
    template = await make_template(client, company_id, auth_headers, code="named-theirs")
    resolve = resolver(client, app, tenant_id, company_id)
    # Storing such a version is refused (assert_layout_references); a layout that names one
    # anyway, by any route, still resolves only to MISSING.
    from design.api.printing import printable_assets

    with tenant_scope(tenant_id):
        async with app.state.session_factory() as db:
            [row] = await printable_assets(db, tmp_path, company_id, canvas(asset_id=theirs["id"]))
    assert row.status == "MISSING" and row.content_base64 is None
    assert (await resolve()).status_code == 200
    assert template["id"]


async def test_a_preview_resolves_one_unpublished_version_and_says_so(
    client, app, tenant_id, company_id, auth_headers
):
    template = await make_template(client, company_id, auth_headers, code="preview-me")
    resolve = resolver(client, app, tenant_id, company_id)
    preview = {"template_id": template["id"], "version_id": template["initial_version_id"]}
    result = await resolve(preview=preview)
    assert result.status_code == 200, result.text
    assert result.json()["source"] == "CUSTOM" and result.json()["preview"] is True
    assert result.json()["version_id"] == template["initial_version_id"]
    assert result.json()["assignment_rule_id"] is None
    # Ordinary resolution is untouched: nothing routes to it, so the standard layout prints.
    ordinary = await resolve()
    assert ordinary.json()["source"] == "BUILTIN" and ordinary.json()["preview"] is False


async def test_a_preview_of_another_companys_or_another_templates_version_is_not_found(
    client, app, tenant_id, company_id, signed_headers, auth_headers
):
    other_company = uuid7()
    theirs = await make_template(
        client, other_company, signed_headers(tenant_id, other_company), code="theirs"
    )
    ours = await make_template(client, company_id, auth_headers, code="ours")
    resolve = resolver(client, app, tenant_id, company_id)
    stolen = await resolve(
        preview={"template_id": theirs["id"], "version_id": theirs["initial_version_id"]}
    )
    assert stolen.status_code == 404
    crossed = await resolve(
        preview={"template_id": ours["id"], "version_id": theirs["initial_version_id"]}
    )
    assert crossed.status_code == 404
    unknown = await resolve(preview={"template_id": ours["id"], "version_id": str(uuid7())})
    assert unknown.status_code == 404

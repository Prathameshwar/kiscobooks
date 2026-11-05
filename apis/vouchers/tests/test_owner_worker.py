import secrets

import httpx
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.owner_snapshot import SnapshotCredential, authorize_snapshot, response_headers
from billing_platform.service_auth import CompanyServiceScope
from conftest import COMPANY, TENANT
from pydantic import SecretStr

from vouchers.tasks.source_worker import Owner, synchronize


async def test_pull_worker_uses_signed_owner_contract_and_rejects_tampering(app):
    credential = SnapshotCredential(
        secret=SecretStr(secrets.token_hex(32)),
        scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),),
    )
    owner = Owner(
        **credential.model_dump(),
        owner="catalog",
        origin="https://catalog.test",
        key_id="catalog.snapshot",
    )

    def respond(request):
        actual, framed, key = authorize_snapshot(
            {owner.key_id: credential},
            owner="catalog",
            tenant_id=TENANT,
            company_id=COMPANY,
            headers=request.headers,
            method=request.method,
            path=request.url.path,
            query=request.url.query.decode(),
            body=request.content,
        )
        body = canonical_json(
            {
                "bundle": {
                    "message_id": str(uuid7()),
                    "tenant_id": str(TENANT),
                    "company_id": str(COMPANY),
                    "definitions": [],
                    "masters": [],
                },
                "next_after": None,
            }
        )
        return httpx.Response(
            200,
            content=body,
            headers=response_headers(
                actual, owner="catalog", key_id=key, request_bytes=framed, body=body
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        # One empty page per Catalog entity: item, item_transaction_policy, item_unit_revision,
        # unit and item_regulatory_classification (Catalog owns dated regulatory history; the
        # worker, apply_bundle and Catalog's snapshot route all list it).
        assert await synchronize(app.state.session_factory, client, owner) == 5


def test_source_origins_do_not_forward_credentials_to_untrusted_destinations():
    import pytest
    from pydantic import ValidationError

    credential = {
        "secret": SecretStr(secrets.token_hex(32)),
        "scopes": (CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),),
        "owner": "catalog",
        "key_id": "catalog.test",
    }
    assert Owner(**credential, origin="http://127.0.0.1:8003").origin == "http://127.0.0.1:8003"
    for origin in (
        "http://remote.test",
        "https://user:pass@remote.test",
        "https://remote.test/path",
        "https://remote.test?query=true",
    ):
        with pytest.raises(ValidationError):
            Owner(**credential, origin=origin)

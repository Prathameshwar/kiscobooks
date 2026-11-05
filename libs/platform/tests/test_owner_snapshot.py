import secrets
import time
import uuid

import pytest
from pydantic import SecretStr

from billing_platform.errors import AuthenticationRequiredError
from billing_platform.owner_snapshot import SnapshotCredential, authorize_snapshot, response_headers
from billing_platform.service_auth import (
    CompanyServiceScope,
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)


def test_scoped_snapshot_request_and_response_bind_every_byte():
    tenant, company = uuid.uuid4(), uuid.uuid4()
    secret = secrets.token_bytes(32).hex()
    credential = SnapshotCredential(
        secret=SecretStr(secret),
        scopes=(CompanyServiceScope(tenant_id=tenant, company_id=company),),
    )
    key_id = "snapshot.test"
    stamp = int(time.time())
    path = "/internal/v1/snapshot"
    framed = service_request_bytes(method="GET", path=path, query="limit=1", body=b"")
    key = ServiceKey("vouchers", "identity", frozenset({"vouchers.snapshot.read"}), secret.encode())
    headers = {
        "x-source-key-id": key_id,
        "x-source-issued-at": str(stamp),
        "x-source-signature": sign_service_body(
            key, key_id=key_id, operation="vouchers.snapshot.read", timestamp=stamp, body=framed
        ),
    }
    arguments = {
        "owner": "identity",
        "tenant_id": tenant,
        "company_id": company,
        "headers": headers,
        "method": "GET",
        "path": path,
        "query": "limit=1",
        "body": b"",
    }
    actual, request, key_name = authorize_snapshot({key_id: credential}, **arguments)
    assert actual == credential and request == framed and key_name == key_id
    for changes in (
        {"company_id": uuid.uuid4()},
        {"query": "limit=2"},
        {"body": b"changed"},
        {"headers": {}},
    ):
        with pytest.raises(AuthenticationRequiredError):
            authorize_snapshot({key_id: credential}, **(arguments | changes))
    response = response_headers(
        credential, owner="identity", key_id=key_id, request_bytes=framed, body=b"facts"
    )
    reply_key = ServiceKey(
        "identity", "vouchers", frozenset({"vouchers.snapshot.response"}), secret.encode()
    )
    verify_service_body(
        {key_id: reply_key},
        key_id=key_id,
        issuer="identity",
        audience="vouchers",
        operation="vouchers.snapshot.response",
        timestamp=response["X-Source-Issued-At"],
        signature=response["X-Source-Signature"],
        body=service_response_bytes(request_bytes=framed, response_body=b"facts"),
        now=stamp,
    )
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize("requester", ["vouchers", "reports"])
def test_shared_snapshot_headers_preserve_audience_and_request_binding(requester):
    from billing_platform.owner_snapshot import request_headers, verify_response

    tenant, company = uuid.uuid4(), uuid.uuid4()
    secret = secrets.token_hex(32)
    credential = SnapshotCredential(
        secret=SecretStr(secret),
        scopes=(CompanyServiceScope(tenant_id=tenant, company_id=company),),
    )
    framed = service_request_bytes(method="GET", path="/head", query="", body=b"")
    headers = request_headers(
        requester=requester,
        owner="accounting",
        key_id="feed.test",
        secret=secret.encode(),
        framed=framed,
    )
    checked, _, _ = authorize_snapshot(
        {"feed.test": credential},
        requester=requester,
        owner="accounting",
        tenant_id=tenant,
        company_id=company,
        headers={key.lower(): value for key, value in headers.items()},
        method="GET",
        path="/head",
        query="",
        body=b"",
    )
    reply = response_headers(
        checked,
        requester=requester,
        owner="accounting",
        key_id="feed.test",
        request_bytes=framed,
        body=b"facts",
    )
    lowered = {key.lower(): value for key, value in reply.items()}
    args = {
        "requester": requester,
        "owner": "accounting",
        "key_id": "feed.test",
        "secret": secret.encode(),
        "framed": framed,
        "body": b"facts",
        "headers": lowered,
    }
    verify_response(**args)
    for changes in (
        {"body": b"tampered"},
        {"framed": b"another request"},
        {"requester": "untrusted"},
        {"headers": {}},
    ):
        with pytest.raises(AuthenticationRequiredError):
            verify_response(**(args | changes))


def test_automatic_snapshot_scope_still_requires_native_enrollment_and_signed_request():
    from billing_platform.owner_snapshot import request_headers
    from pydantic import ValidationError

    tenant, company = uuid.uuid4(), uuid.uuid4()
    secret, key_id = secrets.token_hex(32), "enrollment.test"
    credential = SnapshotCredential(secret=SecretStr(secret), allow_enrolled_companies=True)
    path = "/internal/v1/voucher-sources/" + str(tenant) + "/" + str(company) + "/item"
    framed = service_request_bytes(method="GET", path=path, query="", body=b"")
    signed = request_headers(
        requester="vouchers", owner="catalog", key_id=key_id, secret=secret.encode(), framed=framed
    )
    arguments = {
        "owner": "catalog",
        "tenant_id": tenant,
        "company_id": company,
        "headers": {key.lower(): value for key, value in signed.items()},
        "method": "GET",
        "path": path,
        "query": "",
        "body": b"",
    }
    with pytest.raises(AuthenticationRequiredError):
        authorize_snapshot({key_id: credential}, **arguments)
    assert authorize_snapshot({key_id: credential}, **arguments, enrolled=True)[0] == credential
    with pytest.raises(AuthenticationRequiredError):
        authorize_snapshot(
            {key_id: credential}, **(arguments | {"path": path + "-changed"}), enrolled=True
        )
    with pytest.raises(ValidationError):
        SnapshotCredential(secret=SecretStr(secret))

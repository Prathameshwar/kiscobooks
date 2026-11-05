from typing import Any

import pytest

from billing_platform.errors import AuthenticationRequiredError
from billing_platform.service_auth import (
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)


def test_authenticated_sender_and_every_binding() -> None:
    key = ServiceKey("identity", "catalog", frozenset({"company.snapshot"}), b"unit-test-key" * 4)
    signature = sign_service_body(
        key, key_id="current", operation="company.snapshot", timestamp=1000, body=b"{}"
    )
    args: dict[str, Any] = {
        "key_id": "current",
        "issuer": "identity",
        "audience": "catalog",
        "operation": "company.snapshot",
        "timestamp": "1000",
        "signature": signature,
        "body": b"{}",
        "now": 1000,
    }
    assert verify_service_body({"current": key}, **args).issuer == "identity"
    assert "unit-test-key" not in repr(key)
    for name, value in [
        ("key_id", "retired"),
        ("issuer", "billing"),
        ("audience", "reports"),
        ("operation", "policy.ack"),
        ("timestamp", "1000.0"),
        ("timestamp", "939"),
        ("timestamp", "1061"),
        ("signature", "0" * 64),
        ("body", b'{"changed":true}'),
        ("body", b"x" * 1_048_577),
    ]:
        with pytest.raises(AuthenticationRequiredError):
            verify_service_body({"current": key}, **{**args, name: value})
    with pytest.raises(ValueError):
        verify_service_body({"current": key}, **args, maximum_age=301)


@pytest.mark.parametrize("change", ["secret", "issuer", "audience", "operations"])
def test_invalid_service_configuration(change: str) -> None:
    args: dict[str, Any] = {
        "issuer": "identity",
        "audience": "catalog",
        "operations": frozenset({"company.snapshot"}),
        "secret": b"test-key" * 4,
    }
    args[change] = (
        b"short" if change == "secret" else frozenset() if change == "operations" else "bad\nname"
    )
    with pytest.raises(ValueError):
        ServiceKey(**args)


@pytest.mark.parametrize(
    "changes",
    [{"key_id": "BAD"}, {"operation": "ungranted"}, {"timestamp": -1}, {"body": b"x" * 1_048_577}],
)
def test_signing_rejects_invalid_context(changes: dict[str, Any]) -> None:
    key = ServiceKey("identity", "catalog", frozenset({"company.snapshot"}), b"test-key" * 4)
    args: dict[str, Any] = {
        "key_id": "current",
        "operation": "company.snapshot",
        "timestamp": 1000,
        "body": b"{}",
    }
    with pytest.raises(ValueError):
        sign_service_body(key, **{**args, **changes})


def test_http_signatures_bind_method_path_query_body_and_response_request() -> None:
    key = ServiceKey("catalog", "identity", frozenset({"source.read"}), b"test-key" * 4)
    request: dict[str, Any] = {
        "method": "GET",
        "path": "/source/one",
        "query": "page=1",
        "body": b"",
    }
    original = service_request_bytes(**request)
    signature = sign_service_body(
        key, key_id="current", operation="source.read", timestamp=1000, body=original
    )
    for field, changed in [
        ("method", "POST"),
        ("path", "/source/two"),
        ("query", "page=2"),
        ("body", b"{}"),
    ]:
        mutated = service_request_bytes(**{**request, field: changed})
        with pytest.raises(AuthenticationRequiredError):
            verify_service_body(
                {"current": key},
                key_id="current",
                issuer="catalog",
                audience="identity",
                operation="source.read",
                timestamp="1000",
                signature=signature,
                body=mutated,
                now=1000,
            )
        assert service_response_bytes(
            request_bytes=original, response_body=b"{}"
        ) != service_response_bytes(request_bytes=mutated, response_body=b"{}")
    assert service_response_bytes(
        request_bytes=original, response_body=b"{}"
    ) != service_response_bytes(request_bytes=original, response_body=b"[]")
    for field, changed in [
        ("method", "HEAD"),
        ("path", "relative"),
        ("path", "/" * 2049),
        ("query", "x" * 4097),
        ("path", "/bad\npath"),
        ("query", "bad\rquery"),
        ("body", b"x" * 1048577),
    ]:
        with pytest.raises(ValueError):
            service_request_bytes(**{**request, field: changed})
    for request_bytes, response_body in [(b"x" * 8193, b""), (b"", b"x" * 1048577)]:
        with pytest.raises(ValueError):
            service_response_bytes(request_bytes=request_bytes, response_body=response_body)


def test_service_grants_require_explicit_real_tenant_and_company() -> None:
    import uuid

    from pydantic import ValidationError

    from billing_platform.service_auth import CompanyServiceScope

    tenant, company = uuid.uuid4(), uuid.uuid4()
    assert CompanyServiceScope(tenant_id=tenant, company_id=company).company_id == company
    for values in (
        {"tenant_id": uuid.UUID(int=0), "company_id": company},
        {"tenant_id": tenant, "company_id": uuid.UUID(int=0)},
    ):
        with pytest.raises(ValidationError):
            CompanyServiceScope.model_validate(values)

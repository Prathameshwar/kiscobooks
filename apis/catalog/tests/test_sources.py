import datetime as dt

import pytest
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from pydantic import ValidationError

from catalog.domain.sources import (
    SOURCE_CONTRACTS,
    SourceUnavailableError,
    require_fresh_source,
    version_action,
)
from catalog.schemas.sources import (
    CustomerPricingReference,
    CustomerTypeReference,
    PartyReference,
    SourceBarrier,
)


def common() -> dict[str, object]:
    return {
        "tenant_id": uuid7(),
        "company_id": uuid7(),
        "id": uuid7(),
        "source_version": 1,
        "deleted": False,
    }


def test_source_references_preserve_ownership_without_financial_fields() -> None:
    party = {
        **common(),
        "display_name": "Supplier",
        "is_active": True,
        "is_customer": False,
        "is_supplier": True,
    }
    assert PartyReference.model_validate(party).is_supplier
    for field in ("balance", "actual_cost", "stock", "tax_registration"):
        with pytest.raises(ValidationError):
            PartyReference.model_validate({**party, field: "forbidden"})
    for field, value in (
        ("source_version", True),
        ("tenant_id", "00000000-0000-0000-0000-000000000000"),
        ("deleted", "false"),
    ):
        with pytest.raises(ValidationError):
            PartyReference.model_validate({**party, field: value})
    assert CustomerTypeReference.model_validate(
        {**common(), "code": "A", "name": "Retail", "is_active": True}
    )
    assert CustomerPricingReference.model_validate(
        {**common(), "party_id": uuid7(), "customer_type_id": None, "is_active": True}
    )
    with pytest.raises(ValidationError):
        CustomerPricingReference.model_validate(
            {
                **common(),
                "party_id": "00000000-0000-0000-0000-000000000000",
                "customer_type_id": None,
                "is_active": True,
            }
        )
    assert all(
        contract.adopted_version == (1 if contract.owner == "identity" else None)
        for contract in SOURCE_CONTRACTS
    )


def test_barrier_distinguishes_known_empty_and_incomplete() -> None:
    values = {
        "producer": "identity",
        "stream": "identity.company",
        "contract_version": 1,
        "tenant_id": uuid7(),
        "company_id": uuid7(),
        "snapshot_id": uuid7(),
        "watermark": 5,
        "generated_at": dt.datetime.now(dt.UTC),
        "complete": True,
        "record_count": 0,
        "content_sha256": "a" * 64,
    }
    assert SourceBarrier.model_validate(values).record_count == 0
    for field, value in [
        ("stream", "billing.party"),
        ("generated_at", dt.datetime(2026, 1, 1)),
        ("complete", False),
        ("watermark", 0),
    ]:
        with pytest.raises(ValidationError):
            SourceBarrier.model_validate({**values, field: value})


def test_versions_tombstones_and_freshness_fail_closed() -> None:
    assert (
        version_action(
            existing_version=None, existing_digest=None, incoming_version=1, incoming_digest="a"
        )
        == "apply"
    )
    assert (
        version_action(
            existing_version=2, existing_digest="b", incoming_version=3, incoming_digest="c"
        )
        == "apply"
    )
    assert (
        version_action(
            existing_version=2, existing_digest="b", incoming_version=1, incoming_digest="a"
        )
        == "ignore"
    )
    assert (
        version_action(
            existing_version=2, existing_digest="b", incoming_version=2, incoming_digest="b"
        )
        == "ignore"
    )
    with pytest.raises(ConflictError):
        version_action(
            existing_version=2, existing_digest="b", incoming_version=2, incoming_digest="forged"
        )
    with pytest.raises(ValidationFailedError):
        version_action(
            existing_version=None, existing_digest=None, incoming_version=0, incoming_digest="a"
        )
    now = dt.datetime.now(dt.UTC)
    for complete, generated in [
        (False, now),
        (True, None),
        (True, now + dt.timedelta(seconds=1)),
        (True, now - dt.timedelta(minutes=10)),
        (True, now.replace(tzinfo=None)),
    ]:
        with pytest.raises(SourceUnavailableError):
            require_fresh_source(
                complete=complete,
                generated_at=generated,
                maximum_age=dt.timedelta(minutes=1),
                now=now,
            )
    require_fresh_source(
        complete=True, generated_at=now, maximum_age=dt.timedelta(minutes=1), now=now
    )
    with pytest.raises(ValueError):
        require_fresh_source(complete=True, generated_at=now, maximum_age=dt.timedelta(0), now=now)


def test_barrier_boolean_and_version_constants_are_strict() -> None:
    base = {
        "producer": "identity",
        "stream": "identity.company",
        "contract_version": 1,
        "tenant_id": uuid7(),
        "company_id": uuid7(),
        "snapshot_id": uuid7(),
        "watermark": 5,
        "generated_at": dt.datetime.now(dt.UTC),
        "complete": True,
        "record_count": 0,
        "content_sha256": "a" * 64,
    }
    for field, value in [
        ("contract_version", True),
        ("contract_version", "1"),
        ("complete", 1),
        ("complete", "true"),
    ]:
        with pytest.raises(ValidationError):
            SourceBarrier.model_validate({**base, field: value})

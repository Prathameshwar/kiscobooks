import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError
from reporting_contract.gst import GstReturnRecord

from accounting.schemas.gst_return import GstRecordDetail


def values(**extra):
    return dict(
        registration_id=uuid.uuid4(),
        event_date="2026-10-01",
        return_date="2026-10-01",
        category="4A5",
        source_entity="EXTERNAL",
        reference="import-evidence",
        evidence_hash="a" * 64,
        explanation="Verified source document",
        **extra,
    )


def test_contract_rejects_approximate_money():
    with pytest.raises(ValidationError):
        GstReturnRecord(**values(igst=1.1))


def test_contract_handles_invalid_decimal_as_validation_error():
    with pytest.raises(ValidationError):
        GstReturnRecord(**values(igst="invalid"))


def test_reclaim_requires_original_evidence():
    with pytest.raises(ValidationError):
        GstReturnRecord(**(values() | {"category": "4D1"}))


def test_native_detail_retains_exact_money():
    detail = GstRecordDetail(
        **values(igst=Decimal("18.1234")),
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        row_version=1,
        created_at="2026-10-01T00:00:00Z",
        updated_at="2026-10-01T00:00:00Z",
    )
    assert detail.igst == "18.1234"

import datetime as dt
import uuid

import pytest
from pydantic import ValidationError

from identity.schemas.company_gst_filing import GstFilingCreate


@pytest.mark.parametrize(
    "frequency,start,end",
    [
        ("MONTHLY", "2026-10-01", "2026-11-01"),
        ("QRMP", "2026-10-01", "2027-01-01"),
    ],
)
def test_complete_period_boundaries(frequency, start, end):
    preference = GstFilingCreate(
        registration_id=uuid.uuid4(), frequency=frequency, valid_from=start, valid_to=end
    )
    assert preference.valid_from == dt.date.fromisoformat(start)


@pytest.mark.parametrize(
    "frequency,start,end",
    [
        ("MONTHLY", "2026-10-02", None),
        ("QRMP", "2026-11-01", None),
        ("QRMP", "2026-10-01", "2026-11-01"),
        ("MONTHLY", "2026-10-01", "2026-10-01"),
    ],
)
def test_partial_periods_are_rejected(frequency, start, end):
    with pytest.raises(ValidationError):
        GstFilingCreate(
            registration_id=uuid.uuid4(), frequency=frequency, valid_from=start, valid_to=end
        )

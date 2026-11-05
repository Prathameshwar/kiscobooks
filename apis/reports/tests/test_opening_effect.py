import pytest

from reports.domain.reporting.opening import opening_effect


@pytest.mark.parametrize(
    "kind,original,original_kind,expected",
    [
        ("OPENING", False, None, True),
        ("MANUAL", False, None, False),
        ("REVERSAL", False, None, False),
        ("REVERSAL", True, "MANUAL", False),
        ("REVERSAL", True, "OPENING", True),
        ("MANUAL", True, "OPENING", False),
    ],
)
def test_opening_classification(kind, original, original_kind, expected):
    assert opening_effect(kind, original, original_kind) is expected


def test_reversal_original_is_required_when_referenced():
    with pytest.raises(ValueError, match="original journal"):
        opening_effect("REVERSAL", True, None)

import datetime as dt

import pytest
from billing_platform.errors import ConflictError

from catalog.domain.categories import boundaries, cardinality


@pytest.mark.parametrize(
    "mode,flags",
    [("SINGLE", []), ("SINGLE", [False]), ("SINGLE", [True]), ("MULTIPLE", [False, True, False])],
)
def test_valid_cardinality(mode: str, flags: list[bool]) -> None:
    cardinality(mode, flags)


@pytest.mark.parametrize(
    "mode,flags", [("OTHER", []), ("SINGLE", [False, False]), ("MULTIPLE", [True, True])]
)
def test_invalid_cardinality(mode: str, flags: list[bool]) -> None:
    with pytest.raises(ConflictError):
        cardinality(mode, flags)


def test_sweep_includes_ends_starts_and_date_max_without_overflow() -> None:
    today = dt.date(2090, 1, 1)
    tomorrow = today + dt.timedelta(days=1)
    assert boundaries(
        [
            (today, today),
            (tomorrow, None),
            (dt.date(2080, 1, 1), dt.date(2089, 1, 1)),
            (dt.date.max, dt.date.max),
        ],
        today,
    ) == [today, tomorrow, dt.date.max]

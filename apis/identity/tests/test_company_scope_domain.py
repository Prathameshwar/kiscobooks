"""``domain/company_scope`` — no database, no app (CLAUDE.md §7)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from billing_platform.authz import Grant, Scope
from billing_platform.constants import SCOPE_ALL

from identity.domain.company_scope import scoped_company_ids

TODAY = dt.date(2026, 10, 22)
ALPHA, BETA = uuid.uuid4(), uuid.uuid4()


def company_grant(company_id: uuid.UUID, **overrides: object) -> Grant:
    values: dict[str, object] = {
        "permissions": frozenset({"company.read"}),
        "scope": Scope("company", company_id),
        "valid_from": dt.date(2000, 1, 1),
    }
    return Grant(**(values | overrides))  # type: ignore[arg-type]  # kwargs are the field types


def test_tenant_wide_holder_is_not_narrowed() -> None:
    """``None`` means every company, which is the opposite of an empty set."""
    grants = (
        Grant(frozenset({"company.read"}), Scope("tenant", SCOPE_ALL), dt.date(2000, 1, 1)),
        company_grant(ALPHA),
    )
    assert scoped_company_ids(grants, "company.read", on_date=TODAY) is None


def test_only_company_scoped_grants_carrying_the_permission_contribute() -> None:
    grants = (
        company_grant(ALPHA),
        company_grant(BETA, permissions=frozenset({"company.update"})),
        Grant(frozenset({"company.read"}), Scope("department", uuid.uuid4()), dt.date(2000, 1, 1)),
    )
    # A department grant does not imply its company: `ScopePath` narrows downward only,
    # so reading one department cannot become reading the company that contains it.
    assert scoped_company_ids(grants, "company.read", on_date=TODAY) == frozenset({ALPHA})


@pytest.mark.parametrize(
    "overrides",
    [
        {"is_active": False},
        {"valid_to": dt.date(2026, 10, 21)},
        {"valid_from": dt.date(2026, 10, 23)},
    ],
)
def test_revoked_or_out_of_window_grants_narrow_to_nothing(overrides: dict[str, object]) -> None:
    """Empty, not ``None``: the caller must return an empty page, never every company."""
    result = scoped_company_ids((company_grant(ALPHA, **overrides),), "company.read", on_date=TODAY)
    assert result == frozenset()


def test_no_grants_at_all_narrows_to_nothing() -> None:
    assert scoped_company_ids((), "company.read", on_date=TODAY) == frozenset()


def test_unknown_permission_key_raises_rather_than_returning_nothing() -> None:
    """A typo must fail loudly; silently narrowing to nothing reads as a real refusal."""
    with pytest.raises(ValueError, match="not in the code catalogue"):
        scoped_company_ids((company_grant(ALPHA),), "company.reed", on_date=TODAY)

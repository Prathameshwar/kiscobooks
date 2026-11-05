"""Schema conventions, asserted against the metadata rather than trusted.

These run over every mapped table in the process, so a service importing
``billing_platform`` and adding a table gets the same checks for free. The
tenant-exemption one is the reason the file exists: exemption by *omission* is
how a table quietly leaves the isolation boundary.
"""

from __future__ import annotations

import re

from sqlalchemy import Date, DateTime, Float, Numeric
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import class_mapper
from sqlalchemy.orm.exc import UnmappedClassError

from billing_platform.constants import MONEY_PRECISION, MONEY_SCALE
from billing_platform.db.base import NAMING_CONVENTION, Base
from billing_platform.db.mixins import SelfTenantMixin, TenantMixin
from billing_platform.db.platform_models import TENANT_FILTER_EXEMPT
from billing_platform.db.types import Money, Quantity, UtcDateTime
from tests.helpers import table_of

#: Tables that exist only to exercise the library. Real tables are never added
#: here — a service table with no ``TenantMixin`` belongs in
#: ``TENANT_FILTER_EXEMPT`` with its reason, or it is a review failure.
_FIXTURE_TABLES = {"exempt_thing", "place_like"}

#: ``valid_from``/``valid_to`` are the ``EffectiveMixin`` pair. They are business
#: dates but read as a range, not as a single event date.
_DATE_SUFFIX_EXEMPT = {"valid_from", "valid_to"}

#: The two suffixes docs/identity-schema.md §0.1 allows on a business date.
#: ``_on`` reads better where the date names an event rather than a period —
#: ``trial_ends_on``. Both are accepted; a bare name is not.
_DATE_SUFFIXES = ("_date", "_on")

_TABLE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def _models() -> list[type[Base]]:
    found: list[type[Base]] = []
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        try:
            class_mapper(cls)
        except UnmappedClassError:  # pragma: no cover - defensive
            continue
        found.append(cls)
    return found


def test_every_table_is_tenant_scoped_or_explicitly_exempt() -> None:
    """Exemption is a whitelist with a stated reason, never omission.

    ``SelfTenantMixin`` counts as scoped: ``tenant`` has no ``tenant_id`` because
    its own ``id`` is one, and the session filter applies to it on that column.
    """
    offenders = []
    for model in _models():
        table = table_of(model).name
        if issubclass(model, TenantMixin | SelfTenantMixin):
            continue
        if table in TENANT_FILTER_EXEMPT or table in _FIXTURE_TABLES:
            continue
        offenders.append(table)

    assert offenders == [], (
        f"tables outside the tenant filter with no stated reason: {offenders}. "
        "Add TenantMixin, or add the table to TENANT_FILTER_EXEMPT with why."
    )


def test_every_exemption_states_a_reason() -> None:
    assert all(reason.strip() for reason in TENANT_FILTER_EXEMPT.values())


def test_exemption_list_matches_the_documented_set() -> None:
    """docs/identity-schema.md §0.3 is the authority; drift here means the doc
    and the code disagree about the isolation boundary."""
    assert set(TENANT_FILTER_EXEMPT) == {
        "country",
        "state",
        "currency",
        "language",
        "processed_message",
        "outbox",
        "reference_cache_generation",
        "reference_revision",
        "reference_sync_state",
        "reference_change",
        "local_identity",
        "local_credential",
        "local_recovery_token",
        "local_signing_key",
        "local_authorization",
        "local_refresh_token",
    }


def test_table_names_are_singular_snake_case() -> None:
    for table in Base.metadata.tables:
        assert _TABLE_NAME.match(table), table
        assert not table.endswith("ies"), f"{table} looks plural"


def test_no_float_column_anywhere() -> None:
    """Money and quantities are DECIMAL(19,4). A float column is a silent
    rounding bug that surfaces as a subledger that will not tie."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            assert not isinstance(column.type, Float), f"{table.name}.{column.name}"


def test_every_money_and_quantity_column_is_decimal_19_4() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if not isinstance(column.type, Money | Quantity):
                continue
            impl = column.type.impl
            assert isinstance(impl, Numeric)
            assert (impl.precision, impl.scale) == (MONEY_PRECISION, MONEY_SCALE), (
                f"{table.name}.{column.name} must never narrow the storage scale; "
                "MariaDB truncates to a smaller scale without erroring"
            )


def test_every_timestamp_column_ends_in_at() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, UtcDateTime | DateTime):
                assert column.name.endswith("_at"), f"{table.name}.{column.name}"


def test_every_timestamp_column_uses_the_utc_type() -> None:
    """Not a bare ``DateTime``: the UTC type rejects a naive value on bind."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if column.name.endswith("_at"):
                assert isinstance(column.type, UtcDateTime), f"{table.name}.{column.name}"


def test_every_date_column_reads_as_a_business_date() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, Date) and not isinstance(column.type, DateTime):
                assert (
                    column.name.endswith(_DATE_SUFFIXES) or column.name in _DATE_SUFFIX_EXEMPT
                ), f"{table.name}.{column.name}"


def test_no_mysql_enum_column() -> None:
    """Enums are VARCHAR plus app validation. Altering a MySQL ENUM rebuilds the
    whole table, which is not acceptable on a posted-data table."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            assert not isinstance(column.type, mysql.ENUM), f"{table.name}.{column.name}"


def test_naming_convention_is_applied_to_the_metadata() -> None:
    """Without it, MariaDB invents constraint names and a downgrade cannot drop
    them by name."""
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    assert set(NAMING_CONVENTION) == {"ix", "uq", "fk", "pk", "ck"}


def test_every_table_has_a_primary_key() -> None:
    for table in Base.metadata.tables.values():
        assert list(table.primary_key.columns), table.name

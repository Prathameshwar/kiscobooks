import datetime as dt
from typing import Any

import pytest
from billing_platform.constants import SCOPE_ALL
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from pydantic import ValidationError

from catalog.schemas.identity_source import FACTS, CompanyFact, IdentityChange, validate_facts
from tests.source_factories import all_facts, change, company_record, snapshot


@pytest.mark.parametrize(
    "updates",
    [
        {"first_posted_at": dt.datetime(2026, 1, 1)},
        {"timezone": "unknown/place"},
        {"fiscal_year_start_month": 2, "fiscal_year_start_day": 31},
        {"amount_precision": True},
    ],
)
def test_company_source_requires_exact_calendar_and_numeric_types(updates: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CompanyFact.model_validate({**company_record(uuid7()).data, **updates})
    assert (
        CompanyFact.model_validate(
            {
                **company_record(uuid7()).data,
                "first_posted_at": dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            }
        ).first_posted_at
        is not None
    )


def test_minimal_subject_facts_require_valid_scope_and_lifecycle() -> None:
    rows = {row.kind: row for row in all_facts(uuid7(), uuid7())}
    cases: list[tuple[str, dict[str, Any]]] = [
        ("feature", {"locked_at": "2026-01-01T00:00:00Z", "is_enabled": False}),
        ("field_policy", {"subject_id": str(SCOPE_ALL)}),
        ("field_policy", {"scope_type": "company", "scope_id": str(SCOPE_ALL)}),
        ("role_assignment", {"role_id": str(SCOPE_ALL)}),
        ("role_assignment", {"valid_to": "1999-01-01"}),
        ("group_member", {"user_id": str(SCOPE_ALL)}),
    ]
    for kind, updates in cases:
        with pytest.raises(ValidationError):
            FACTS[kind].model_validate({**rows[kind].data, **updates})


def test_complete_sources_reject_missing_streams_tombstones_and_foreign_scopes() -> None:
    tenant, company = uuid7(), uuid7()
    source = snapshot(tenant, company, all_facts(company, uuid7()))
    for manifest in (
        source.manifest.model_copy(update={"contract": "unknown.v1"}),
        source.manifest.model_copy(update={"stream_counts": {}}),
        source.manifest.model_copy(
            update={"stream_counts": {**source.manifest.stream_counts, "company": 0}}
        ),
    ):
        with pytest.raises(ValueError):
            validate_facts(manifest, source.records)
    cases = [
        SnapshotRecord(kind="company", id=uuid7(), data=company_record(company).data),
        SnapshotRecord(kind="company", id=company, deleted=True, data={}),
        SnapshotRecord(kind="unknown", id=uuid7(), data={}),
    ]
    rows = {row.kind: row for row in source.records}
    cases.extend(
        [
            SnapshotRecord(
                kind="feature",
                id=uuid7(),
                data={**rows["feature"].data, "company_id": str(uuid7())},
            ),
            SnapshotRecord(
                kind="field_policy",
                id=uuid7(),
                data={
                    **rows["field_policy"].data,
                    "scope_type": "department",
                    "scope_id": str(uuid7()),
                },
            ),
        ]
    )
    for invalid in cases:
        with pytest.raises(ValueError):
            validate_facts(source.manifest, (invalid,))
    validate_facts(source.manifest, source.records)


def test_changes_require_contiguous_versions_unique_identities_and_known_kinds() -> None:
    tenant = uuid7()
    for update in (
        {"tenant_id": SCOPE_ALL},
        {"previous_version": 1, "source_version": 3},
        {"records": [SnapshotRecord(kind="unknown", id=uuid7(), data={})]},
    ):
        with pytest.raises(ValidationError):
            IdentityChange.model_validate({**change(tenant, 3).model_dump(), **update})
    row = SnapshotRecord(kind="user", id=uuid7(), deleted=True, data={})
    assert change(tenant, 3, (row,)).records[0].deleted
    with pytest.raises(ValidationError):
        change(tenant, 3, (row, row))

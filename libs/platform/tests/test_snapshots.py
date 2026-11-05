import datetime as dt
from typing import Any

import pytest
from pydantic import ValidationError

from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.snapshots import (
    SnapshotManifest,
    SnapshotPage,
    SnapshotRecord,
    manifest_digest,
    paginate_records,
    verify_pages,
)


def manifest(pages: tuple[SnapshotPage, ...], **changes: Any) -> SnapshotManifest:
    now = dt.datetime.now(dt.UTC)
    digests = tuple(page.digest() for page in pages)
    count = sum(len(page.records) for page in pages)
    return SnapshotManifest.model_validate(
        {
            "contract": "test.source.v1",
            "snapshot_id": pages[0].snapshot_id if pages else uuid7(),
            "tenant_id": uuid7(),
            "company_id": uuid7(),
            "source_version": 1,
            "generated_at": now,
            "expires_at": now + dt.timedelta(seconds=60),
            "record_count": count,
            "page_sha256": digests,
            "content_sha256": manifest_digest(digests),
            "stream_counts": {"test": count, "empty": 0},
            **changes,
        }
    )


def test_snapshot_pages_are_bounded_and_complete_empty_is_distinct_from_missing() -> None:
    records = tuple(
        SnapshotRecord(kind="test", id=uuid7(), data={"text": "value"}) for _ in range(129)
    )
    pages = paginate_records(uuid7(), records)
    assert len(pages) == 2
    frozen = manifest(pages)
    assert verify_pages(frozen, pages) == records
    assert verify_pages(manifest(()), ()) == ()
    for bad in [pages[:1], pages[::-1], (pages[0], pages[0]), (*pages, pages[1])]:
        with pytest.raises(ValidationFailedError):
            verify_pages(frozen, bad)
    wrong = pages[0].model_copy(update={"snapshot_id": uuid7()})
    with pytest.raises(ValidationFailedError):
        verify_pages(frozen, (wrong, pages[1]))
    with pytest.raises(ValidationFailedError):
        paginate_records(uuid7(), (records[0], records[0]))
    duplicate_pages = (
        pages[0],
        SnapshotPage(snapshot_id=pages[0].snapshot_id, page_number=1, records=(records[0],)),
    )
    with pytest.raises(ValidationFailedError):
        verify_pages(manifest(duplicate_pages), duplicate_pages)
    with pytest.raises(ValidationFailedError):
        verify_pages(manifest(pages, stream_counts={"unexpected": 129}), pages)


def test_manifest_and_record_strictness_and_payload_bounds() -> None:
    changes: list[dict[str, Any]] = [
        {"source_version": True},
        {"record_count": 1},
        {"stream_counts": {"test": True}},
        {"generated_at": dt.datetime(2026, 1, 1)},
        {"content_sha256": "0" * 64},
        {"page_sha256": ["bad"]},
        {"company_id": "00000000-0000-0000-0000-000000000000"},
        {"expires_at": dt.datetime(2000, 1, 1, tzinfo=dt.UTC)},
    ]
    for change in changes:
        with pytest.raises(ValidationError):
            manifest((), **change)
    cases: list[dict[str, Any]] = [
        {"id": "00000000-0000-0000-0000-000000000000"},
        {"deleted": True},
        {"data": {"large": "x" * (512 * 1024)}},
        {"data": {"float": 0.1}},
    ]
    for values in cases:
        with pytest.raises(ValidationError):
            SnapshotRecord.model_validate(
                {"kind": "test", "id": uuid7(), "data": {"x": "y"}, **values}
            )
    assert SnapshotRecord(kind="test", id=uuid7(), deleted=True, data={}).deleted
    big = tuple(
        SnapshotRecord(kind="test", id=uuid7(), data={"large": "x" * 300_000}) for _ in range(2)
    )
    assert len(paginate_records(uuid7(), big)) == 2
    with pytest.raises(ValidationFailedError):
        paginate_records(
            uuid7(), (SnapshotRecord(kind="test", id=uuid7(), data={}) for _ in range(10_001))
        )
    with pytest.raises(ValidationFailedError):
        paginate_records(
            uuid7(),
            (
                SnapshotRecord(kind="test", id=uuid7(), data={"large": "x" * 300_000})
                for _ in range(30)
            ),
        )


def test_transport_enforces_snapshot_total_and_page_size_bounds() -> None:
    import uuid

    snapshot_id = uuid7()
    assert paginate_records(snapshot_id, ()) == ()
    with pytest.raises(ValidationError):
        SnapshotPage(
            snapshot_id=uuid.UUID(int=0),
            page_number=0,
            records=(SnapshotRecord(kind="test", id=uuid7(), data={}),),
        )
    with pytest.raises(ValidationError):
        SnapshotPage(
            snapshot_id=snapshot_id,
            page_number=0,
            records=tuple(
                SnapshotRecord(kind="test", id=uuid7(), data={"text": "x" * 5000})
                for _ in range(128)
            ),
        )
    pages = tuple(
        SnapshotPage(
            snapshot_id=snapshot_id,
            page_number=i,
            records=(SnapshotRecord(kind="test", id=uuid7(), data={"text": "x" * 300000}),),
        )
        for i in range(29)
    )
    with pytest.raises(ValidationFailedError, match="total transport"):
        verify_pages(manifest(pages), pages)

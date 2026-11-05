"""Bounded immutable snapshot transport. Owners supply only approved payload fields."""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from collections.abc import Iterable
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from billing_platform.errors import ValidationFailedError
from billing_platform.idempotency import canonical_json

MAX_RECORDS = 10_000
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_PAGE_BYTES = 512 * 1024
MAX_PAGE_RECORDS = 128


class SnapshotRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    id: uuid.UUID
    deleted: StrictBool = False
    data: dict[str, Any]

    @model_validator(mode="after")
    def identity_and_tombstone(self) -> Self:
        if self.id.int == 0 or (self.deleted and self.data):
            raise ValueError("real identity and empty tombstone payload required")
        if len(canonical_json(self.model_dump(mode="json"))) > MAX_PAGE_BYTES - 1024:
            raise ValueError("source record exceeds transport bound")
        return self


class SnapshotPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    snapshot_id: uuid.UUID
    page_number: int = Field(strict=True, ge=0, le=MAX_RECORDS)
    records: tuple[SnapshotRecord, ...] = Field(min_length=1, max_length=MAX_PAGE_RECORDS)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if self.snapshot_id.int == 0 or len(self.wire_bytes()) > MAX_PAGE_BYTES:
            raise ValueError("invalid or oversized snapshot page")
        return self

    def wire_bytes(self) -> bytes:
        return canonical_json(self.model_dump(mode="json"))

    def digest(self) -> str:
        return hashlib.sha256(self.wire_bytes()).hexdigest()


class SnapshotManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract: str = Field(pattern=r"^[a-z][a-z0-9_.]{0,119}$")
    snapshot_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    source_version: int = Field(strict=True, ge=1, le=2**63 - 1)
    generated_at: dt.datetime
    expires_at: dt.datetime
    record_count: int = Field(strict=True, ge=0, le=MAX_RECORDS)
    page_sha256: tuple[str, ...] = Field(max_length=MAX_RECORDS)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    # Counts include every stream, including known-empty ones.
    stream_counts: dict[str, Annotated[int, Field(strict=True, ge=0, le=MAX_RECORDS)]]

    @field_validator("generated_at", "expires_at")
    @classmethod
    def aware(cls, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None:
            raise ValueError("aware source instants required")
        return value.astimezone(dt.UTC)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if any(
            identifier.int == 0
            for identifier in (self.snapshot_id, self.tenant_id, self.company_id)
        ):
            raise ValueError("non-nil snapshot scope required")
        if not self.generated_at < self.expires_at <= self.generated_at + dt.timedelta(minutes=5):
            raise ValueError("source freshness must be positive and no more than five minutes")
        if sum(self.stream_counts.values()) != self.record_count:
            raise ValueError("source counts differ from manifest")
        if any(
            len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
            for digest in self.page_sha256
        ):
            raise ValueError("invalid page digest")
        if self.content_sha256 != manifest_digest(self.page_sha256):
            raise ValueError("manifest content digest differs")
        return self


def manifest_digest(page_digests: tuple[str, ...]) -> str:
    return hashlib.sha256(canonical_json(list(page_digests))).hexdigest()


def paginate_records(
    snapshot_id: uuid.UUID, records: Iterable[SnapshotRecord]
) -> tuple[SnapshotPage, ...]:
    pages: list[SnapshotPage] = []
    current: list[SnapshotRecord] = []
    current_bytes = 0
    total_bytes = 0
    identities: set[tuple[str, uuid.UUID]] = set()
    for record in records:
        identity = record.kind, record.id
        if identity in identities or len(identities) >= MAX_RECORDS:
            raise ValidationFailedError("duplicate or excessive source records")
        identities.add(identity)
        size = len(canonical_json(record.model_dump(mode="json"))) + 1
        total_bytes += size
        if total_bytes > MAX_SNAPSHOT_BYTES:
            raise ValidationFailedError("snapshot exceeds bounded workflow size")
        if current and (
            len(current) >= MAX_PAGE_RECORDS or current_bytes + size > MAX_PAGE_BYTES - 1024
        ):
            pages.append(
                SnapshotPage(
                    snapshot_id=snapshot_id, page_number=len(pages), records=tuple(current)
                )
            )
            current, current_bytes = [], 0
        current.append(record)
        current_bytes += size
    if current:
        pages.append(
            SnapshotPage(snapshot_id=snapshot_id, page_number=len(pages), records=tuple(current))
        )
    return tuple(pages)


def verify_pages(
    manifest: SnapshotManifest, pages: Iterable[SnapshotPage]
) -> tuple[SnapshotRecord, ...]:
    result: list[SnapshotRecord] = []
    seen: set[tuple[str, uuid.UUID]] = set()
    counts = {key: 0 for key in manifest.stream_counts}
    number = 0
    total_bytes = 0
    for page in pages:
        if (
            number >= len(manifest.page_sha256)
            or page.page_number != number
            or page.snapshot_id != manifest.snapshot_id
            or page.digest() != manifest.page_sha256[number]
        ):
            raise ValidationFailedError("snapshot page sequence or digest differs")
        total_bytes += sum(
            len(canonical_json(record.model_dump(mode="json"))) + 1 for record in page.records
        )
        if total_bytes > MAX_SNAPSHOT_BYTES:
            raise ValidationFailedError("snapshot exceeds its total transport bound")
        for record in page.records:
            identity = record.kind, record.id
            if identity in seen or record.kind not in counts:
                raise ValidationFailedError("duplicate identity or unknown stream in snapshot")
            seen.add(identity)
            counts[record.kind] += 1
            result.append(record)
        number += 1
    if (
        number != len(manifest.page_sha256)
        or len(result) != manifest.record_count
        or counts != manifest.stream_counts
    ):
        raise ValidationFailedError("snapshot is incomplete")
    return tuple(result)

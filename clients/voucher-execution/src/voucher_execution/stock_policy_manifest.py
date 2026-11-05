"""Pure canonical manifest fingerprint shared by the policy owner and consumer."""

import hashlib
import uuid
from collections.abc import Collection, Mapping, Sequence
from typing import Protocol, TypeVar

from billing_platform.idempotency import canonical_json

Key = TypeVar("Key", bound=str)


class PolicyEntry(Protocol):
    @property
    def warehouse_id(self) -> uuid.UUID: ...

    @property
    def revision(self) -> int: ...

    @property
    def flags(self) -> Collection[str]: ...


def policy_manifest_digest(
    entries: Sequence[PolicyEntry],
    defaults: Mapping[Key, uuid.UUID | None],
    keys: Collection[Key],
) -> str:
    return hashlib.sha256(
        canonical_json(
            {
                "locations": [
                    {
                        "warehouse_id": str(row.warehouse_id),
                        "revision": row.revision,
                        "flags": sorted(row.flags),
                    }
                    for row in sorted(
                        entries, key=lambda entry: entry.warehouse_id.bytes
                    )
                ],
                "defaults": {
                    key: None if defaults.get(key) is None else str(defaults[key])
                    for key in sorted(keys)
                },
            }
        )
    ).hexdigest()

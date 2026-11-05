"""Short-lived, actor-bound review proofs for category governance."""

import hashlib
import hmac
from typing import Any
from zoneinfo import ZoneInfo

from billing_platform.db.types import utcnow
from billing_platform.idempotency import canonical_json
from billing_platform.pagination import CursorCodec
from pydantic_core import to_jsonable_python

from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.policy_state import policy_state


def codec(access: ConfigurationAccess, secret: bytes, subject: str) -> CursorCodec:
    return CursorCodec(
        hmac.digest(secret, b"catalog.category-review.v1", hashlib.sha256),
        context=f"category-review:{access.actor.tenant_id}:{access.company}:{access.actor.user_id}:{subject}",
        ttl_seconds=900,
    )


async def stamp(
    access: ConfigurationAccess, model: type[Any], body: dict[str, Any], evidence: list[Any]
) -> dict[str, Any]:
    context = await access.context(model)
    state = await policy_state(access.db, access.actor, access.company, lock=False)
    generation = state.generation if state is not None else 1
    values = {
        "input": body,
        "generation": generation,
        "source": context.source_version,
        "date": str(utcnow().astimezone(ZoneInfo(context.company.timezone)).date()),
    }
    digest = hashlib.sha256(canonical_json(values))
    unique = {(row.__tablename__, str(row.id)): row for row in evidence}
    for (entity, object_id), row in sorted(unique.items()):
        digest.update(
            canonical_json(
                to_jsonable_python(
                    {"entity": entity, "id": object_id, "values": await access.values(row)}
                )
            )
        )
    return {
        "digest": digest.hexdigest(),
        "generation": generation,
        "source": context.source_version,
    }

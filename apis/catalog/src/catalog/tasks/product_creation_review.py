"""Verify reviewed configuration values while allowing equivalent source refreshes."""

import hashlib
import json
import uuid

from billing_platform.errors import ConflictError
from billing_platform.gateway import Actor
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.schemas.configuration import EffectiveConfiguration, EffectiveQuery
from catalog.schemas.products import FamilyCreate
from catalog.tasks.configuration_resolution import resolve

FIELDS = {
    "company_id",
    "as_of",
    "kind",
    "sources",
    "options",
    "numeric_defaults",
    "profiles",
    "pricing",
}


def configuration_fingerprint(value: EffectiveConfiguration) -> str:
    payload = value.model_dump(mode="json", include=FIELDS)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


async def reviewed_source(
    db: AsyncSession, actor: Actor, company: uuid.UUID, body: FamilyCreate
) -> int | None:
    setup = body.initial_setup
    if setup is None or setup.configuration_fingerprint is None:
        return None
    current = await resolve(
        db,
        actor,
        company,
        EffectiveQuery(
            as_of=setup.effective_from,
            kind=body.kind,
            product_type_revision_id=body.product_type_revision_id,
            group_id=setup.group_id,
        ),
    )
    if (
        current.policy_generation != setup.expected_generation
        or configuration_fingerprint(current) != setup.configuration_fingerprint
    ):
        raise ConflictError(
            "Product configuration changed. Refresh configuration and review your draft.",
            fields={
                "initial_setup.units": (
                    "Refresh configuration and review the updated product options before creating."
                )
            },
        )
    # Current permissions, fields, references and commercial rules are still checked by
    # every native handler. No publication or money guard is weakened globally.
    return current.source_version

"""Signed, expiring adoption previews and immutable per-SKU source pins."""

import datetime as dt
import hashlib
import hmac
import uuid

from billing_platform.authz import ScopePath
from billing_platform.errors import ConflictError
from billing_platform.gateway import Actor
from billing_platform.idempotency import canonical_json
from billing_platform.pagination import CursorCodec
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.product_definitions import (
    ProductConfigurationAdoption,
    ProductConfigurationAdoptionSource,
)
from catalog.schemas.configuration import EffectiveConfiguration
from catalog.schemas.product_authoring import AdoptionCommit, AdoptionPreview
from catalog.tasks.product_commands import ProductWork
from catalog.tasks.product_requirements import group_on, pinned, product_work, requirements


def codec(secret: bytes, actor: Actor, company: uuid.UUID, item_id: uuid.UUID) -> CursorCodec:
    return CursorCodec(
        hmac.digest(secret, b"catalog.adoption.v1", hashlib.sha256),
        context=f"adoption:{actor.tenant_id}:{company}:{actor.user_id}:{item_id}",
        ttl_seconds=900,
    )


async def prepare(
    work: ProductWork,
    as_of: dt.date,
    secret: bytes,
    *,
    item_version: int | None = None,
    for_activation: bool = False,
) -> tuple[AdoptionPreview, EffectiveConfiguration]:
    assert work.item is not None
    work.actor.require_scope(
        "product_configuration.adopt", target=ScopePath(company_id=work.company)
    )
    if for_activation:
        work.actor.require_scope("item.activate", target=ScopePath(company_id=work.company))
    allowed_families = {"DRAFT", "ACTIVE"} if for_activation else {"DRAFT"}
    blocked = []
    if work.item.status != "DRAFT" or work.family.status not in allowed_families:
        blocked.append("active_structural_adoption_unsupported")
    definition, effective = await requirements(work, as_of, proposed=True)
    _, old = await pinned(work, as_of)
    version = work.item.row_version if item_version is None else item_version
    value = {
        "resolution_version": 2,
        "family": str(work.family.id),
        "family_version": work.family.row_version,
        "item_version": version,
        # Equivalent source refreshes retain the review; all resolved values,
        # source revisions and policy generation remain bound to this token.
        "configuration": effective.model_dump(mode="json", exclude={"source_version"}),
        "missing": definition.missing,
        "for_activation": for_activation,
        "blocked": blocked,
    }
    digest = hashlib.sha256(canonical_json(value)).hexdigest()
    result = AdoptionPreview(
        item_id=work.item.id,
        expected_version=version,
        eligible=not definition.missing and not blocked,
        blocked_reasons=blocked,
        purpose="ACTIVATION" if for_activation else "DRAFT_CONFIGURATION",
        missing=definition.missing,
        preview_token=codec(secret, work.actor, work.company, work.item.id).encode(
            {"digest": digest}
        ),
        current_revision_ids=list(old),
        proposed_revision_ids=[row.revision_id for row in effective.sources],
        policy_generation=effective.policy_generation,
        source_version=effective.source_version,
    )
    return result, effective


async def preview(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    item_id: uuid.UUID,
    as_of: dt.date,
    secret: bytes,
) -> AdoptionPreview:
    result, _ = await prepare(await product_work(db, actor, company, item_id), as_of, secret)
    return result


async def adopt(
    work: ProductWork,
    body: AdoptionCommit,
    secret: bytes,
    *,
    for_activation: bool = False,
    prepared: tuple[AdoptionPreview, EffectiveConfiguration] | None = None,
) -> None:
    assert work.item is not None
    verified = codec(secret, work.actor, work.company, work.item.id).decode(body.preview_token)
    # Activation has just prepared this tuple under the same company lock and work context.
    # Standalone adoption requests always revalidate their caller-supplied preview here.
    if prepared is not None and not for_activation:
        raise ValueError("prepared adoption is only available inside activation")
    fresh, effective = (
        prepared
        if prepared is not None
        else await prepare(
            work,
            body.as_of,
            secret,
            item_version=body.expected_version,
            for_activation=for_activation,
        )
    )
    current = codec(secret, work.actor, work.company, work.item.id).decode(fresh.preview_token)
    if verified != current:
        raise ConflictError("configuration adoption preview is stale; preview again")
    if not fresh.eligible:
        raise ConflictError("product definition requirements must be satisfied before adoption")
    latest = await work.db.scalar(
        select(func.max(ProductConfigurationAdoption.revision)).where(
            ProductConfigurationAdoption.company_id == work.company,
            ProductConfigurationAdoption.item_id == work.item.id,
        )
    )
    last_date = await work.db.scalar(
        select(func.max(ProductConfigurationAdoption.effective_on)).where(
            ProductConfigurationAdoption.company_id == work.company,
            ProductConfigurationAdoption.item_id == work.item.id,
        )
    )
    if (latest or 0) >= 2**31 - 1 or (last_date is not None and body.as_of < last_date):
        raise ConflictError("adoption cannot replace prior effective history")
    group = await group_on(work, body.as_of)
    row = await work.new(
        ProductConfigurationAdoption,
        item_id=work.item.id,
        revision=(latest or 0) + 1,
        effective_on=body.as_of,
        product_type_revision_id=work.family.product_type_revision_id,
        group_assignment_id=group.id if group else None,
        source_version=fresh.source_version,
        policy_generation=fresh.policy_generation,
        resolution_version=2,
        preview_hash=bytes.fromhex(current["digest"]),
    )
    # The company lock keeps the just-validated source set stable through commit.
    sources = [
        await work.new(
            ProductConfigurationAdoptionSource,
            adoption_id=row.id,
            scope_id=source.scope_id,
            revision_id=source.revision_id,
        )
        for source in effective.sources
    ]
    work.db.add(row)
    await work.db.flush([row])
    work.db.add_all(sources)

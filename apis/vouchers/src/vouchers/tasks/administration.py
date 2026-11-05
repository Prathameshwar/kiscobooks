"""Shared company administration; all mutations run under the company fence."""

import uuid
from typing import Any

from billing_platform.errors import ConflictError, ValidationFailedError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.invoice import SALES_CONFIGURATION_FIELDS, InvoicePolicy

from vouchers.api.auth import Access
from vouchers.domain.configuration import (
    digest,
    intersect,
    policy_wire,
    validate_policy,
    validate_sales_policy,
)
from vouchers.domain.registry import FOUNDATION_SECTIONS, resolve_kind
from vouchers.models import core as m
from vouchers.schemas.configuration import (
    BindingCreate,
    ClassCreate,
    ConfigurationCreate,
    Policy,
    TypeCreate,
    TypeRevise,
)
from vouchers.schemas.documents import SeriesCreate, TemplateCreate
from vouchers.tasks.access import authorize, denied
from vouchers.tasks.common import audit, expected, get, values


async def validate_policy_references(db: AsyncSession, current: Access, policy: Policy) -> None:
    """JSON policy references must belong to the current company and be active."""
    series_ids = set(policy.allowed_series_ids or ())
    if policy.default_series_id is not None:
        series_ids.add(policy.default_series_id)
    template_ids = set(policy.allowed_template_revision_ids or ())
    if policy.default_template_revision_id is not None:
        template_ids.add(policy.default_template_revision_id)
    if series_ids:
        found = set(
            await db.scalars(
                select(m.VoucherNumberSeries.id).where(
                    m.VoucherNumberSeries.company_id == current.context.company_id,
                    m.VoucherNumberSeries.id.in_(series_ids),
                    m.VoucherNumberSeries.status == "ACTIVE",
                )
            )
        )
        if found != series_ids:
            raise ValidationFailedError("configured issue series is unavailable")
    if template_ids:
        found = set(
            await db.scalars(
                select(m.VoucherTemplateRevision.id)
                .join(
                    m.VoucherTemplate,
                    (m.VoucherTemplate.id == m.VoucherTemplateRevision.template_id)
                    & (m.VoucherTemplate.company_id == m.VoucherTemplateRevision.company_id),
                )
                .where(
                    m.VoucherTemplateRevision.company_id == current.context.company_id,
                    m.VoucherTemplateRevision.id.in_(template_ids),
                    m.VoucherTemplate.status == "ACTIVE",
                )
            )
        )
        if found != template_ids:
            raise ValidationFailedError("configured template revision is unavailable")
    if policy.invoice is not None:
        account_ids = set(policy.invoice.sales_party_account_ids or ()) | set(
            policy.invoice.sales_supply_account_ids or ()
        )
        if account_ids:
            found = set(
                await db.scalars(
                    select(m.VoucherMasterEvidence.source_id).where(
                        m.VoucherMasterEvidence.company_id == current.context.company_id,
                        m.VoucherMasterEvidence.owner == "accounting",
                        m.VoucherMasterEvidence.entity_type == "account",
                        m.VoucherMasterEvidence.source_id.in_(account_ids),
                        m.VoucherMasterEvidence.status == "ACTIVE",
                    )
                )
            )
            if found != account_ids:
                raise ValidationFailedError("configured sales account is unavailable")


async def type_create(db: AsyncSession, current: Access, body: TypeCreate) -> m.VoucherType:
    policy = body.policy
    if (
        (body.kind, body.profile) == ("PURCHASE", "STANDARD")
        and body.derived_from_revision_id is None
        and "policy" not in body.model_fields_set
    ):
        policy = policy.model_copy(update={"invoice": InvoicePolicy()})
    source = None
    if body.derived_from_revision_id is not None:
        source = await get(db, current, m.VoucherTypeRevision, body.derived_from_revision_id)
        parent = await get(db, current, m.VoucherType, source.type_id)
        if parent.status != "ACTIVE" or (parent.kind, parent.profile) != (body.kind, body.profile):
            raise ConflictError("clone source is retired or has different behavior")
        policy = intersect(Policy.model_validate(source.policy), body.policy)
    validate_policy(body.kind, body.profile, policy)
    row = m.VoucherType(
        **values(current),
        code=body.code,
        name=body.name,
        kind=body.kind,
        profile=body.profile,
        status="ACTIVE",
        current_revision=1,
    )
    db.add(row)
    await db.flush()
    await type_revision(db, current, row, policy)
    if source is not None:
        db.add(
            m.VoucherTypeOrigin(
                **values(current),
                type_id=row.id,
                source_revision_id=source.id,
                source_content_hash=source.content_hash,
            )
        )
    audit(db, current, "type", row.id, "create")
    return row


async def type_revision(
    db: AsyncSession, current: Access, row: m.VoucherType, policy: Any
) -> m.VoucherTypeRevision:
    validate_policy(row.kind, row.profile, policy)
    await validate_policy_references(db, current, policy)
    return await write_type_revision(db, row, policy, actor_user_id=current.actor.user_id)


async def write_type_revision(
    db: AsyncSession, row: m.VoucherType, policy: Policy, *, actor_user_id: uuid.UUID | None
) -> m.VoucherTypeRevision:
    """Persist a validated native revision for user administration or fixed provisioning."""
    from billing_platform.ids import uuid7

    def metadata() -> dict[str, Any]:
        return {
            "id": uuid7(),
            "tenant_id": row.tenant_id,
            "company_id": row.company_id,
            "created_by": actor_user_id,
            "updated_by": actor_user_id,
        }

    wire = policy_wire(policy)
    revision = m.VoucherTypeRevision(
        **metadata(),
        type_id=row.id,
        revision_number=row.current_revision,
        policy=wire,
        content_hash=digest(wire),
    )
    db.add(revision)
    await db.flush()
    spec = resolve_kind(row.kind, row.profile)
    for section in sorted(spec.sections | FOUNDATION_SECTIONS):
        requirement = (
            "FORBIDDEN"
            if section not in spec.sections or section in policy.forbidden_sections
            else "REQUIRED"
            if section in policy.required_sections
            else "OPTIONAL"
        )
        db.add(
            m.VoucherTypeSection(
                **metadata(),
                type_revision_id=revision.id,
                section=section,
                requirement=requirement,
                minimum_stage="SUBMITTED",
            )
        )
    return revision


async def type_revise(
    db: AsyncSession, current: Access, object_id: uuid.UUID, body: TypeRevise
) -> m.VoucherType:
    row = await get(db, current, m.VoucherType, object_id, lock=True)
    expected(row, body.expected_version)
    if row.status != "ACTIVE":
        raise ConflictError("voucher type retired")
    row.current_revision += 1
    row.row_version += 1
    await type_revision(db, current, row, body.policy)
    audit(db, current, "type", row.id, "revise")
    return row


def validate_family_policy(family: str, policy: Policy) -> None:
    if family == "PURCHASE" and policy.sales_workflow is not None:
        raise ValidationFailedError("Sales workflow controls require a Sales or common family")
    if family != "PURCHASE" and policy.purchase_calculation is not None:
        raise ValidationFailedError("calculation presets require a Purchase configuration family")
    if (
        family != "SALES"
        and policy.invoice is not None
        and (SALES_CONFIGURATION_FIELDS & policy.invoice.model_dump(mode="json").keys())
    ):
        raise ValidationFailedError("Sales-only controls require a Sales configuration family")
    if family == "SALES":
        validate_sales_policy(policy)


async def configuration_create(
    db: AsyncSession, current: Access, body: ConfigurationCreate
) -> m.VoucherConfigurationProfile:
    validate_family_policy(body.family, body.policy)
    await validate_policy_references(db, current, body.policy)
    row = m.VoucherConfigurationProfile(
        **values(current),
        code=body.code,
        name=body.name,
        family=body.family,
        status="ACTIVE",
        current_revision=1,
    )
    db.add(row)
    await db.flush()
    wire = policy_wire(body.policy)
    db.add(
        m.VoucherConfigurationRevision(
            **values(current),
            profile_id=row.id,
            revision_number=1,
            status="DRAFT",
            policy=wire,
            content_hash=digest(wire),
        )
    )
    audit(db, current, "configuration", row.id, "create")
    return row


async def configuration_revise(
    db: AsyncSession, current: Access, object_id: uuid.UUID, body: TypeRevise
) -> m.VoucherConfigurationProfile:
    row = await get(db, current, m.VoucherConfigurationProfile, object_id, lock=True)
    validate_family_policy(row.family, body.policy)
    await validate_policy_references(db, current, body.policy)
    expected(row, body.expected_version)
    if row.status != "ACTIVE":
        raise ConflictError("configuration retired")
    row.current_revision += 1
    row.row_version += 1
    wire = policy_wire(body.policy)
    db.add(
        m.VoucherConfigurationRevision(
            **values(current),
            profile_id=row.id,
            revision_number=row.current_revision,
            status="DRAFT",
            policy=wire,
            content_hash=digest(wire),
        )
    )
    audit(db, current, "configuration", row.id, "revise")
    return row


async def bind(
    db: AsyncSession, current: Access, type_id: uuid.UUID | None, body: BindingCreate
) -> m.VoucherConfigurationBinding:
    revision = await get(
        db, current, m.VoucherConfigurationRevision, body.configuration_revision_id
    )
    profile = await get(db, current, m.VoucherConfigurationProfile, revision.profile_id, lock=True)
    if revision.status != "PUBLISHED" or profile.status != "ACTIVE":
        raise ConflictError("publish configuration before binding")
    if type_id:
        kind = await get(db, current, m.VoucherType, type_id, lock=True)
        expected(kind, body.expected_version)
        if profile.family not in {"COMMON", kind.kind}:
            raise ValidationFailedError("configuration family is incompatible")
        validate_policy(kind.kind, kind.profile, Policy.model_validate(revision.policy))
        kind.row_version += 1
    else:
        expected(profile, body.expected_version)
        profile.row_version += 1
    start = body.valid_from
    end = body.valid_to
    if end and end <= start:
        raise ValidationFailedError("invalid binding dates")
    statement = select(m.VoucherConfigurationBinding.id).where(
        m.VoucherConfigurationBinding.company_id == current.context.company_id,
        m.VoucherConfigurationBinding.type_id == type_id,
        m.VoucherConfigurationBinding.family == profile.family,
        or_(
            m.VoucherConfigurationBinding.valid_to.is_(None),
            m.VoucherConfigurationBinding.valid_to > start,
        ),
    )
    if end:
        statement = statement.where(m.VoucherConfigurationBinding.valid_from < end)
    if await db.scalar(statement.limit(1)):
        raise ConflictError("overlapping configuration binding")
    row = m.VoucherConfigurationBinding(
        **values(current),
        configuration_revision_id=revision.id,
        type_id=type_id,
        family=profile.family,
        valid_from=start,
        valid_to=end,
    )
    db.add(row)
    audit(db, current, "configuration", profile.id, "bind")
    return row


async def class_create(
    db: AsyncSession, current: Access, type_id: uuid.UUID, body: ClassCreate
) -> m.VoucherClass:
    row = await get(db, current, m.VoucherType, type_id, lock=True)
    expected(row, body.expected_version)
    revision = await db.scalar(
        select(m.VoucherTypeRevision).where(
            m.VoucherTypeRevision.company_id == current.context.company_id,
            m.VoucherTypeRevision.type_id == row.id,
            m.VoucherTypeRevision.revision_number == row.current_revision,
        )
    )
    if revision is None:
        raise ConflictError("type revision missing")
    from vouchers.schemas.configuration import Policy

    validate_policy(
        row.kind, row.profile, intersect(Policy.model_validate(revision.policy), body.policy)
    )
    await validate_policy_references(db, current, body.policy)
    cls = m.VoucherClass(
        **values(current),
        type_revision_id=revision.id,
        code=body.code,
        name=body.name,
        policy=policy_wire(body.policy),
    )
    db.add(cls)
    row.row_version += 1
    audit(db, current, "type", row.id, "class_create")
    return cls


async def series_create(
    db: AsyncSession, current: Access, body: SeriesCreate
) -> m.VoucherNumberSeries:
    row = m.VoucherNumberSeries(**values(current), **body.model_dump(), status="ACTIVE")
    db.add(row)
    audit(db, current, "series", row.id, "create")
    return row


async def template_create(
    db: AsyncSession, current: Access, body: TemplateCreate
) -> m.VoucherTemplate:
    row = m.VoucherTemplate(**values(current), code=body.code, status="ACTIVE")
    db.add(row)
    await db.flush()
    db.add(
        m.VoucherTemplateRevision(
            **values(current),
            template_id=row.id,
            revision_number=1,
            title=body.title,
            fields=list(body.fields),
            content_hash=digest(body.model_dump(mode="json")),
        )
    )
    audit(db, current, "template", row.id, "create")
    return row


async def detail(
    db: AsyncSession, current: Access, model: Any, object_id: uuid.UUID
) -> dict[str, Any]:
    authorize(current, "read")
    row = await get(db, current, model, object_id)
    keys = {
        "id",
        "company_id",
        "row_version",
        "status",
        "code",
        "name",
        "kind",
        "profile",
        "current_revision",
        "revision_number",
        "policy",
        "prefix",
        "padding",
        "type_revision_id",
        "family",
    }
    result = {key: getattr(row, key) for key in keys if hasattr(row, key)}
    if isinstance(row, m.VoucherType):
        origin = await db.scalar(
            select(m.VoucherTypeOrigin).where(
                m.VoucherTypeOrigin.company_id == current.context.company_id,
                m.VoucherTypeOrigin.type_id == row.id,
            )
        )
        if origin:
            result["derived_from_revision_id"] = origin.source_revision_id
        revision = await db.scalar(
            select(m.VoucherTypeRevision).where(
                m.VoucherTypeRevision.company_id == current.context.company_id,
                m.VoucherTypeRevision.type_id == row.id,
                m.VoucherTypeRevision.revision_number == row.current_revision,
            )
        )
    elif isinstance(row, m.VoucherConfigurationProfile):
        revision = await db.scalar(
            select(m.VoucherConfigurationRevision).where(
                m.VoucherConfigurationRevision.company_id == current.context.company_id,
                m.VoucherConfigurationRevision.profile_id == row.id,
                m.VoucherConfigurationRevision.revision_number == row.current_revision,
            )
        )
    elif isinstance(row, m.VoucherTemplate):
        revision = await db.scalar(
            select(m.VoucherTemplateRevision).where(
                m.VoucherTemplateRevision.company_id == current.context.company_id,
                m.VoucherTemplateRevision.template_id == row.id,
                m.VoucherTemplateRevision.revision_number == 1,
            )
        )
    else:
        revision = None
    if revision:
        result["revision_id"] = revision.id
        for key in ("policy", "title", "fields"):
            if hasattr(revision, key):
                result[key] = getattr(revision, key)
    if denied(current, "vouchers.configuration", set(result), "read", result):
        from billing_platform.errors import PermissionDeniedError

        raise PermissionDeniedError("configuration fields are not readable")
    return result

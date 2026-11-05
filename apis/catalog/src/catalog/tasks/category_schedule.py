"""Review and append dated category sets without rewriting active-family history."""

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError

from catalog.domain.categories import CategoryCardinalityError
from catalog.models.classification import CategoryScheme
from catalog.models.product_definitions import FamilyCategory
from catalog.models.products import Item, ProductFamily
from catalog.schemas.product_authoring import CategoryAssignmentInput, CategoryAssignmentPreview
from catalog.tasks.category_membership import references, rows
from catalog.tasks.category_review import codec, stamp
from catalog.tasks.product_commands import ProductWork


async def validate(work: ProductWork, body: CategoryAssignmentInput) -> tuple[list[Any], list[Any]]:
    work.actor.require_scope("item.update", target=ScopePath(company_id=work.company))
    await work.access.require(work.family)
    if work.family.status not in {"DRAFT", "ACTIVE"}:
        raise ConflictError("category maintenance requires a current family")
    if len({entry.category_id for entry in body.categories}) != len(body.categories):
        raise ValidationFailedError("category memberships must be distinct")
    try:
        evidence = await references(work.access, body.categories)
    except CategoryCardinalityError as exc:
        raise ValidationFailedError(str(exc)) from exc
    history = await rows(work.access, FamilyCategory, FamilyCategory.family_id == work.family.id)
    # Old dependencies are also protected, including memberships removed by the replacement.
    evidence.extend(await references(work.access, history, active=False))
    if work.family.status == "ACTIVE":
        context = await work.access.context(ProductFamily)
        today = utcnow().astimezone(ZoneInfo(context.company.timezone)).date()
        if body.valid_from is None or body.valid_from <= today:
            raise ConflictError("active-family categories require a strictly future start date")
        if any(
            row.valid_from >= body.valid_from
            or (row.valid_to is not None and row.valid_to >= body.valid_from - dt.timedelta(days=1))
            for row in history
        ):
            raise ConflictError("append the new category set after all scheduled memberships")
        if not body.categories and not any(row.valid_to is None for row in history):
            raise ConflictError("category set is already scheduled to be empty")
        required = await rows(
            work.access,
            CategoryScheme,
            CategoryScheme.is_active.is_(True),
            CategoryScheme.is_required.is_(True),
        )
        evidence.extend(required)
        if {row.id for row in required} - {entry.scheme_id for entry in body.categories}:
            raise ConflictError("category set omits a required scheme")
        from catalog.tasks.product_requirements import configuration

        items = await rows(
            work.access, Item, Item.family_id == work.family.id, Item.status == "ACTIVE"
        )
        if len(items) > 128:
            raise ConflictError("category maintenance exceeds the active SKU review limit")
        evidence.extend(items)
        for item in items:
            child = ProductWork(work.db, work.actor, work.company, work.family, item, work.access)
            effective = await configuration(child, body.valid_from)
            mode = effective.options.category_mode
            if (mode == "DISABLED" and body.categories) or (
                mode == "REQUIRED" and not body.categories
            ):
                raise ConflictError("category replacement violates an active SKU configuration")
    if body.categories:
        from catalog.tasks.product_choices import require_choice

        await require_choice(work, "category", as_of=body.valid_from)
    context = await work.access.context(FamilyCategory)
    for row in history:
        before = await work.access.values(row)
        if work.family.status == "DRAFT":
            context.assert_writable(frozenset(before), before=before, after={})
        elif row.valid_to is None:
            assert body.valid_from is not None
            context.assert_writable(
                frozenset({"valid_to", "row_version"}),
                before=before,
                after={
                    **before,
                    "valid_to": body.valid_from - dt.timedelta(days=1),
                    "row_version": row.row_version + 1,
                },
            )
    for entry in body.categories:
        values = {
            "family_id": work.family.id,
            "row_version": 1,
            "primary_slot": 1 if entry.is_primary else None,
            "valid_from": body.valid_from or dt.date(1000, 1, 1),
            "valid_to": None,
            **entry.model_dump(),
        }
        context.assert_writable(
            frozenset(key for key, value in values.items() if value is not None),
            before={},
            after=values,
        )
    return history, [*history, *evidence]


async def prepare(
    work: ProductWork, body: CategoryAssignmentInput, secret: bytes, *, writing: bool = False
) -> CategoryAssignmentPreview:
    expected = body.expected_version + int(writing)
    if work.family.row_version != expected:
        raise ConflictError("family version changed; review category replacement again")
    if not writing:
        context = await work.access.context(ProductFamily)
        before = await work.access.values(work.family)
        context.assert_writable(
            frozenset({"row_version"}),
            before=before,
            after={**before, "row_version": body.expected_version + 1},
        )
    history, evidence = await validate(work, body)
    proof = await stamp(
        work.access,
        ProductFamily,
        body.model_dump(mode="json", exclude={"preview_token"}),
        evidence,
    )
    return CategoryAssignmentPreview(
        family_id=work.family.id,
        expected_version=body.expected_version,
        valid_from=body.valid_from,
        membership_count=len(body.categories),
        closing_count=sum(row.valid_to is None for row in history),
        policy_generation=proof["generation"],
        source_version=proof["source"],
        preview_token=codec(work.access, secret, str(work.family.id)).encode(proof),
    )


async def replace(work: ProductWork, body: CategoryAssignmentInput, secret: bytes | None) -> None:
    if work.family.status == "ACTIVE":
        if secret is None or body.preview_token is None:
            raise ConflictError("active-family category maintenance requires a reviewed preview")
        fresh = await prepare(work, body, secret, writing=True)
        proof = codec(work.access, secret, str(work.family.id))
        if proof.decode(body.preview_token) != proof.decode(fresh.preview_token):
            raise ConflictError("category preview changed; review again")
    history, _ = await validate(work, body)
    for row in history:
        if work.family.status == "DRAFT":
            await work.retire_draft(row)
        elif row.valid_to is None:
            assert body.valid_from is not None
            if row.row_version >= 2**31 - 1:
                raise ConflictError("category membership version exhausted")
            before = await work.access.values(row)
            row.valid_to = body.valid_from - dt.timedelta(days=1)
            row.row_version += 1
            row.updated_at, row.updated_by = utcnow(), work.actor.user_id
            await work.record(row, before, "close")
    await work.db.flush()
    for entry in body.categories:
        value = await work.new(
            FamilyCategory,
            family_id=work.family.id,
            primary_slot=1 if entry.is_primary else None,
            valid_from=body.valid_from or dt.date(1000, 1, 1),
            valid_to=None,
            **entry.model_dump(),
        )
        work.db.add(value)
